"""
Vendor Portal Views
===================
Customer login/register ki tarz par vendor ke liye:

- vendor_register  : vendor account banao (admin approve karta hai)
- vendor_login     : phone + password
- vendor_logout
- vendor_dashboard : apne products, status aur stock
- vendor_product_add / vendor_product_edit / vendor_product_toggle
- vendor_orders / vendor_order_action : store ke orders (Accept / Reject / Ready)

Products shop par tab nazar aate hain jab approval_status='approved' aur
is_active=True ho (shop ki purani queries is_active par hi filter karti hain,
isliye pending/rejected products khud ba khud chhupe rehte hain).

Optional settings (settings.py):
    VENDOR_AUTO_APPROVE_ACCOUNTS = False   # True = register hote hi approved
    VENDOR_AUTO_APPROVE_PRODUCTS = False   # True = products foran shop par
"""
import json
import logging
import re
from datetime import time as dtime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from .vendor_access import accessible_profiles, get_vendor_profile, vendor_role
from django.contrib import messages
from django.contrib.auth import authenticate, logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..utils.phone_utils import find_by_phone
from ..shop_flags import flag_required, shop_flag
from ..vendor_commission import (
    base_commission_percent, commission_percent, expire_promos, on_vendor_approved, promo_active, reprice_open_batches, vendor_earnings,
    vendor_share,
)
from ..models import (
    Cuisine,
    Brand, Category, CompanyInfo, DeliveryArea, DeliveryInfo, Inventory, OrderReview, Product, RiderProfile, SaleOrder,
    StockBatch, StoreCategory, Unit, Vendor, VendorDayHours, VendorProfile, VendorStaff, Warehouse,
)
from . import store_orders
from .views_reviews import vendor_rating
from .views_customer_auth import get_client_ip, is_valid_phone, normalize_phone, safe_login

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PRICE = Decimal('99999999.99')
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 10 * 60


# ============================================
# HELPERS
# ============================================

def _auto_approve_accounts():
    return shop_flag('vendor_auto_approve_accounts')


def _auto_approve_products():
    return shop_flag('vendor_auto_approve_products')


def _safe_next(request, value):
    """Sirf apni site ke URL par redirect (open redirect se bachao)."""
    if value and url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return ''


def _company_name():
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def _dispute_pending(vendor):
    from .disputes import needs_response_count
    return needs_response_count('vendor', vendor)


def _get_vendor(request):
    return get_vendor_profile(request.user).vendor


def _login_key(phone, ip):
    return f"vendor_login_fail:{phone}:{ip}"


def _stock_warehouse():
    """Shop jis warehouse se stock check karti hai (customer flow wali)."""
    return Warehouse.objects.first()


def _read_stock(product, warehouse):
    if not warehouse:
        return 0
    inv = Inventory.objects.filter(product=product, warehouse=warehouse).first()
    return inv.stock if inv else 0


def _add_stock(product, warehouse, qty, cost, selling_price):
    """
    Naya stock add karo: Inventory + StockBatch (FIFO sales isi batch se chalti hain).
    StockBatch.save() selling>=cost aur margin policy khud check karta hai
    (ValidationError uthata hai).
    """
    if qty <= 0:
        return
    Inventory.update_stock(product, qty, warehouse)
    StockBatch(
        product=product, qty=qty, remaining_qty=qty, price=cost,
        warehouse=warehouse, selling_price=selling_price,
    ).save()


def _err_text(exc):
    try:
        return '; '.join(exc.messages)
    except Exception:
        return str(exc)


def _validate_image(f):
    """Image size/type check. Error text ya None return karta hai."""
    if f.size > MAX_IMAGE_BYTES:
        return 'Image 5 MB se chhoti honi chahiye'
    try:
        from PIL import Image
        img = Image.open(f)
        img.verify()
        f.seek(0)
    except Exception:
        return 'Valid image upload karein (JPG, PNG, WEBP)'
    return None


def _clean_product_form(request, editing=False, prefix=''):
    """
    POST data validate karo. `prefix` multi-row form ke liye ("p3-" => p3-name, p3-price ...).
    Returns (data dict, errors list).
    """
    post = request.POST
    errors = []

    name = post.get(prefix + 'name', '').strip()[:100]
    if len(name) < 3:
        errors.append('Product ka naam likhein (kam az kam 3 characters)')

    description = post.get(prefix + 'description', '').strip()[:2000]

    category = None
    try:
        category = Category.objects.filter(pk=int(post.get(prefix + 'category', ''))).first()
    except (TypeError, ValueError):
        pass
    if not category:
        errors.append('Category select karein')

    brand = None
    if post.get(prefix + 'brand'):
        try:
            brand = Brand.objects.filter(pk=int(post.get(prefix + 'brand'))).first()
        except (TypeError, ValueError):
            pass

    unit = None
    if post.get(prefix + 'unit'):
        try:
            unit = Unit.objects.filter(pk=int(post.get(prefix + 'unit'))).first()
        except (TypeError, ValueError):
            pass

    try:
        price = Decimal(post.get(prefix + 'price', '').strip())
        if price <= 0 or price > MAX_PRICE:
            raise InvalidOperation
        price = price.quantize(Decimal('0.01'))
    except (InvalidOperation, AttributeError):
        price = None
        errors.append('Enter a valid price (more than 0)')

    try:
        discount = Decimal(post.get(prefix + 'discount_percentage', '').strip() or '0')
        if discount < 0 or discount > 90:
            raise InvalidOperation
    except InvalidOperation:
        discount = Decimal('0')
        errors.append('Discount 0 se 90 ke darmiyan hona chahiye')

    try:
        stock = float(post.get(prefix + 'stock', '').strip() or '0')
        if stock < 0 or stock > 1_000_000:
            raise ValueError
    except ValueError:
        stock = 0
        errors.append('Stock sahi number hona chahiye')
    if not editing and stock <= 0:
        errors.append('Enter stock greater than 0')

    image = request.FILES.get(prefix + 'image')
    if image:
        err = _validate_image(image)
        if err:
            errors.append(err)
    elif not editing:
        errors.append('Product ki image upload karein')

    return {
        'name': name, 'description': description, 'category': category,
        'brand': brand, 'unit': unit, 'price': price, 'discount': discount,
        'stock': stock, 'image': image,
    }, errors


def _form_context(request, product=None, data=None):
    """Form ke liye values: POST wapas (error par) ya product ki maujooda values."""
    warehouse = _stock_warehouse()
    if data is not None:
        v = {k: data.get(k, '') for k in
             ('name', 'description', 'category', 'brand', 'unit', 'price',
              'discount_percentage', 'stock')}
    elif product is not None:
        base_price = product.original_price if product.original_price and product.original_price > 0 else product.price
        v = {
            'name': product.name,
            'description': product.description or '',
            'category': str(product.category_id or ''),
            'brand': str(product.brand_id or ''),
            'unit': str(product.unit_id or ''),
            'price': base_price,
            'discount_percentage': product.discount_percentage,
            'stock': '',
        }
    else:
        v = {k: '' for k in ('name', 'description', 'category', 'brand', 'unit',
                              'price', 'discount_percentage', 'stock')}
    return {
        'page_title': 'Edit Product' if product else 'Add Product',
        'product': product,
        'categories': Category.objects.order_by('name'),
        'brands': Brand.objects.order_by('name'),
        'units': Unit.objects.order_by('name'),
        'v': v,
        'current_stock': _read_stock(product, warehouse) if product else None,
        'commission_percent': commission_percent(get_vendor_profile(request.user)),
        'company_name': _company_name(),
    }


# ============================================
# 1. REGISTER
# ============================================

def _areas_from_post(post):
    """Dropdown/checkbox list se chune hue areas (sirf admin ki list wale), warna purana text field.
    Admin ne list nahi banayi to purana textarea chalta hai."""
    if post.get('areas_mode') == 'pick':
        valid = DeliveryArea.valid_labels()
        picks = [a for a in post.getlist('delivery_areas_pick') if a in valid]
        extra = post.get('delivery_areas_extra', '')
        return ', '.join(picks + ([extra] if extra.strip() else []))
    return post.get('delivery_areas', '')


def _area_context(profile=None):
    """Template ke liye: shehar-wise areas, aur vendor ne jo chune hain."""
    groups = DeliveryArea.grouped()
    chosen = {a.lower() for a in VendorProfile.clean_areas(profile.delivery_areas)} if profile else set()
    listed = {a.label.lower() for _, items in groups for a in items}
    return {
        'area_groups': [(c, [(a.label, a.label.lower() in chosen) for a in items]) for c, items in groups],
        'area_extra': ', '.join(a for a in VendorProfile.clean_areas(profile.delivery_areas)
                                if a.lower() not in listed) if profile else '',
    }


def _pw_min_length():
    """Register page ko wahi minimum lambai dikhao jo server check karta hai."""
    from ..utils.password_policy import MIN_LENGTH
    return MIN_LENGTH


def _launch_offer_banner():
    """Register page par dikhane ke liye: admin ne launch offer on kiya ho to {'days', 'percent'}, warna None."""
    try:
        from .vendor_commission import launch_promo_settings
        cfg = launch_promo_settings()
    except Exception:
        logger.exception('launch_promo_settings failed')
        return None
    return cfg if cfg['days'] > 0 else None


@flag_required('vendor_register_enabled')
def vendor_register(request):
    """Vendor account banao. Admin approve karega (ya auto-approve setting)."""
    if request.user.is_authenticated and (get_vendor_profile(request.user) is not None):
        return redirect('vendor_dashboard')

    if request.method == 'POST':
        business_name = request.POST.get('business_name', '').strip()[:100]
        owner_name = request.POST.get('full_name', '').strip()[:100]
        phone = request.POST.get('phone', '').strip()[:20]
        email = request.POST.get('email', '').strip()[:100]
        city = request.POST.get('city', '').strip()[:100]
        delivery_areas = ', '.join(VendorProfile.clean_areas(_areas_from_post(request.POST)))
        address = request.POST.get('address', '').strip()[:500]
        store_category = StoreCategory.objects.filter(
            pk=request.POST.get('store_category') or 0, is_active=True).first()
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm_password', '')

        def fail(msg):
            messages.error(request, msg)
            return redirect('vendor_register')

        if len(business_name) < 3:
            return fail('❌ Business/Shop ka naam likhein')
        if len(owner_name) < 3:
            return fail('❌ Enter your full name')
        if not phone or not is_valid_phone(phone):
            return fail('❌ Enter a valid phone number')
        try:
            validate_email(email)
        except ValidationError:
            return fail('❌ Enter a valid email address')
        if not city:
            return fail('❌ City likhein')
        if len(address) < 10:
            return fail('❌ Poora address likhein')
        from ..utils.password_policy import first_error as _pw_error
        pw_error = _pw_error(password, (business_name, phone, email))
        if pw_error:
            return fail(f'❌ {pw_error}')
        if password != confirm:
            return fail('❌ Passwords match nahi karte')

        phone = normalize_phone(phone)

        # Blacklist: block kiya hua phone / email / device naya account nahi bana sakta
        from ..utils.blacklist import blocked_identity, current_device, BLOCKED_MSG
        signup_device = current_device(request)
        if blocked_identity(phone=phone, email=email, device=signup_device):
            return fail(BLOCKED_MSG)

        if find_by_phone(Vendor, phone):
            messages.error(request, '⚠️ This phone is already registered')
            return redirect('vendor_login')
        if User.objects.filter(email__iexact=email).exists():
            return fail('⚠️ Ye email pehle se registered hai')

        try:
            with transaction.atomic():
                base = 'vendor_' + phone.replace('+', '')
                username, n = base, 1
                while User.objects.filter(username=username).exists():
                    username = f"{base}_{n}"
                    n += 1

                parts = owner_name.split()
                user = User.objects.create_user(
                    username=username, email=email, password=password,
                    first_name=parts[0],
                    last_name=' '.join(parts[1:]),
                )
                vendor = Vendor.objects.create(
                    name=business_name,
                    contact_number=phone,
                    address=f"{address}, {city}",
                )
                approved = _auto_approve_accounts()
                new_profile = VendorProfile.objects.create(
                    vendor=vendor, user=user, business_name=business_name,
                    city=city, delivery_areas=delivery_areas, store_category=store_category,
                    is_approved=approved,
                    approved_at=now() if approved else None,
                    last_login_at=now(),
                    signup_device=signup_device,
                )
                if approved:   # auto-approve: launch commission offer (agar admin ne on kiya ho)
                    on_vendor_approved(new_profile, first_time=True)
                safe_login(request, user)
                request.session.save()
        except Exception:
            logger.exception("Vendor register error")
            return fail('❌ There was a problem with registration. Please try again')

        # Admin ko alert (kabhi register nahi rokta)
        try:
            from ..utils.admin_alerts import alert_admins
            alert_admins('🏢 Naya vendor register hua',
                         f'{business_name} ({city}), {owner_name}: '
                         + ('auto-approve ho gaya.' if approved else 'approval ka intezar hai.'),
                         link=request.build_absolute_uri(reverse('vendor_approvals') + '?tab=accounts&status=pending'))
        except Exception:
            logger.exception('vendor register admin alert failed')

        if approved:
            messages.success(request, '🎉 Account created! You can now list products.')
        else:
            messages.success(
                request,
                '🎉 Account created! You can list products after admin approval.'
            )
        return redirect('vendor_dashboard')

    return render(request, 'customer_portal/vendor/register.html', {
        'page_title': 'Seller Registration',
        'store_categories': StoreCategory.objects.filter(is_active=True),
        'company_name': _company_name(),
        'launch_offer': _launch_offer_banner(),
        'pw_min': _pw_min_length(),
        **_area_context(),
    })


# ============================================
# 2. LOGIN / LOGOUT
# ============================================

@flag_required('vendor_login_enabled')
def vendor_login(request):
    if request.user.is_authenticated and (get_vendor_profile(request.user) is not None):
        return redirect(_safe_next(request, request.GET.get('next')) or 'vendor_dashboard')

    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        password = request.POST.get('password', '')
        next_url = _safe_next(request, request.POST.get('next') or request.GET.get('next'))

        if not phone_raw or not password:
            messages.error(request, '❌ Enter both phone and password')
            return redirect('vendor_login')

        phone = normalize_phone(phone_raw)
        ip = get_client_ip(request) or ''
        key = _login_key(phone, ip)

        if cache.get(key, 0) >= LOGIN_MAX_ATTEMPTS:
            messages.error(request, '🔒 Too many attempts. Please try again after 10 minutes.')
            return redirect('vendor_login')

        profile = (
            VendorProfile.objects.select_related('user', 'vendor')
            .filter(vendor__contact_number=phone, parent__isnull=True).first()
        )
        user = None
        staff_rec = None
        if profile and profile.user and not (profile.user.is_staff or profile.user.is_superuser):
            user = authenticate(request, username=profile.user.username, password=password)
        elif not profile:
            # Phone kisi owner ka nahi: store ke staff ka ho sakta hai
            staff_rec = (VendorStaff.objects.select_related('user', 'store')
                         .filter(phone=phone, is_active=True).first())
            if staff_rec and staff_rec.user and not (staff_rec.user.is_staff or staff_rec.user.is_superuser):
                user = authenticate(request, username=staff_rec.user.username, password=password)

        if not user:
            cache.set(key, cache.get(key, 0) + 1, LOGIN_LOCK_SECONDS)
            messages.error(request, '❌ Phone or password is incorrect')
            return redirect('vendor_login')

        cache.delete(key)
        safe_login(request, user)
        request.session.save()
        if staff_rec:
            staff_rec.last_login_at = now()
            staff_rec.save(update_fields=['last_login_at'])
            messages.success(request, f'🎉 Welcome, {staff_rec.name}! ({staff_rec.store.business_name})')
            return redirect(next_url or 'vendor_dashboard')
        profile.last_login_at = now()
        profile.save(update_fields=['last_login_at'])
        messages.success(request, f'🎉 Welcome back, {profile.business_name}!')
        return redirect(next_url or 'vendor_dashboard')

    return render(request, 'customer_portal/vendor/login.html', {
        'page_title': 'Seller Login',
        'next': _safe_next(request, request.GET.get('next')),
        'company_name': _company_name(),
    })


def vendor_logout(request):
    request.session.flush()
    logout(request)
    messages.success(request, '👋 You have been logged out.')
    return redirect('shop_home')


# ============================================
# 3. DASHBOARD
# ============================================

@vendor_login_required
def vendor_dashboard(request):
    profile = get_vendor_profile(request.user)
    vendor = profile.vendor

    # Launch promo ki date guzar gayi ho to batches abhi normal rate par aa jayen (cron na chale to bhi)
    try:
        if profile.commission_promo_until and expire_promos(profile):
            profile.refresh_from_db()
    except Exception:
        logger.exception('expire_promos failed (vendor profile=%s)', profile.pk)

    products = list(
        Product.objects.filter(vendor=vendor)
        .select_related('category')
        .annotate(total_stock=Sum('inventory__stock'))
        .order_by('-id')
    )
    counts = {'approved': 0, 'pending': 0, 'rejected': 0}
    from .stock_alerts import effective_level, low_stock_settings, stock_state
    stock_cfg = low_stock_settings()
    stock_level = effective_level(profile, stock_cfg)
    low_count = out_count = 0
    for p in products:
        counts[p.approval_status] = counts.get(p.approval_status, 0) + 1
        p.stock_state = None
        if stock_cfg['enabled'] and p.approval_status == 'approved' and p.is_active:
            p.stock_state = stock_state(p.total_stock, stock_level)
            low_count += p.stock_state == 'low'
            out_count += p.stock_state == 'out'

    return render(request, 'customer_portal/vendor/dashboard.html', {
        'vendor_role': vendor_role(request.user),
        'switch_stores': accessible_profiles(request.user),
        'page_title': 'Vendor Dashboard',
        'profile': profile,
        'products': products,
        'counts': counts,
        'low_count': low_count,
        'out_count': out_count,
        'low_level': stock_level,
        'earnings': vendor_earnings(vendor),
        'payouts': vendor.marketplace_payouts.all()[:10],
        'rating': vendor_rating(vendor),
        'recent_reviews': OrderReview.objects.filter(vendor=vendor, vendor_rating__isnull=False)
                          .select_related('sale_order')[:5],
        'commission_percent': commission_percent(profile),
        'promo': ({'percent': commission_percent(profile), 'normal': base_commission_percent(profile),
                   'until': profile.commission_promo_until}
                  if promo_active(profile) and commission_percent(profile) < base_commission_percent(profile)
                  else None),
        'new_orders': SaleOrder.objects.filter(vendor=vendor, status='pending').count(),
        'dispute_pending': _dispute_pending(vendor),
        'company_name': _company_name(),
    })


# ============================================
# 4. PRODUCTS
# ============================================

MAX_BULK_ROWS = 20                # ek submit mein itne products tak
_ROW_FIELDS = ('name', 'description', 'category', 'brand', 'unit', 'price',
               'discount_percentage', 'stock')


def _blank_values():
    return {k: '' for k in _ROW_FIELDS}


def _row_values(post, prefix):
    """Row ki POST values wapas form mein dikhane ke liye."""
    return {k: post.get(prefix + k, '') for k in _ROW_FIELDS}


def _row_is_blank(request, prefix):
    """Bilkul khali row (sirf category/unit chuni ho) ko ignore karo."""
    if request.FILES.get(prefix + 'image'):
        return False
    return not any(request.POST.get(prefix + f, '').strip()
                   for f in ('name', 'description', 'price', 'stock'))


def _bulk_context(request, rows):
    """Add-products page ka context. rows = [{'id', 'v', 'errors'}]."""
    return {
        'page_title': 'Add Products',
        'rows': rows,
        'blank_row': {'id': '__ID__', 'v': _blank_values(), 'errors': []},
        'next_row_id': max([int(r['id']) for r in rows] + [0]) + 1,
        'max_rows': MAX_BULK_ROWS,
        'categories': Category.objects.order_by('name'),
        'brands': Brand.objects.order_by('name'),
        'units': Unit.objects.order_by('name'),
        'commission_percent': commission_percent(get_vendor_profile(request.user)),
        'company_name': _company_name(),
    }


def _save_new_product(request, profile, warehouse, data):
    """Ek naya product + uska stock save karo (apni transaction mein)."""
    live = _auto_approve_products()
    cost = vendor_share(data['price'], data['discount'], commission_percent(profile))  # vendor ka hissa == shop ka cost
    with transaction.atomic():
        product = Product(
            name=data['name'], description=data['description'],
            category=data['category'], brand=data['brand'], unit=data['unit'],
            original_price=data['price'], price=data['price'],
            discount_percentage=data['discount'],
            image=data['image'],
            vendor=profile.vendor, created_by=request.user,
            approval_status='approved' if live else 'pending',
            is_active=live,
        )
        product.save()
        _add_stock(product, warehouse, data['stock'], cost, data['price'])
    return product


@vendor_login_required
@flag_required('vendor_can_add_products')
def vendor_product_add(request):
    """
    Ek hi page se kai products add karo. Har product apni transaction mein save hota hai:
    jo theek hain wo save ho jate hain, jin mein ghalti ho unhi ki rows error ke saath wapas aati hain.
    """
    profile = get_vendor_profile(request.user)
    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')

    warehouse = _stock_warehouse()
    if not warehouse:
        messages.error(request, '❌ No warehouse is set for the shop. Please contact the admin.')
        return redirect('vendor_dashboard')

    if request.method == 'POST':
        row_ids = []
        for rid in request.POST.getlist('row_ids'):
            if re.fullmatch(r'\d{1,4}', rid) and rid not in row_ids:
                row_ids.append(rid)
        row_ids = row_ids[:MAX_BULK_ROWS]

        saved, failed = 0, []
        for rid in row_ids:
            prefix = f'p{rid}-'
            if _row_is_blank(request, prefix):
                continue
            data, errors = _clean_product_form(request, prefix=prefix)
            if not errors:
                try:
                    _save_new_product(request, profile, warehouse, data)
                    saved += 1
                    continue
                except ValidationError as exc:
                    errors = [_err_text(exc)]
                except Exception:
                    logger.exception("Vendor product add error")
                    errors = ['Could not save the product. Please try again']
            failed.append({'id': rid, 'v': _row_values(request.POST, prefix), 'errors': errors})

        if not saved and not failed:
            messages.error(request, '❌ Enter details for at least one product')
            return render(request, 'customer_portal/vendor/product_bulk_form.html',
                          _bulk_context(request, [{'id': '1', 'v': _blank_values(), 'errors': []}]))

        if saved:
            what = 'Product' if saved == 1 else f'{saved} products'
            if _auto_approve_products():
                messages.success(request, f'✅ {what} listed in the shop!')
            else:
                messages.success(request, f'✅ {what} submitted. They will appear in the shop after admin approval.')

        if failed:
            messages.error(
                request,
                f'❌ {len(failed)} products were not saved. Fix the errors below and submit again '
                f'(image dobara select karni hogi).'
            )
            return render(request, 'customer_portal/vendor/product_bulk_form.html',
                          _bulk_context(request, failed))

        return redirect('vendor_dashboard')

    return render(request, 'customer_portal/vendor/product_bulk_form.html',
                  _bulk_context(request, [{'id': '1', 'v': _blank_values(), 'errors': []}]))


@vendor_login_required
@flag_required('vendor_can_add_products')
def vendor_product_edit(request, pk):
    profile = get_vendor_profile(request.user)
    product = get_object_or_404(Product, pk=pk, vendor=profile.vendor)

    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')

    warehouse = _stock_warehouse()

    if request.method == 'POST':
        data, errors = _clean_product_form(request, editing=True)
        if errors:
            for e in errors:
                messages.error(request, f'❌ {e}')
            return render(request, 'customer_portal/vendor/product_form.html',
                          _form_context(request, product=product, data=request.POST))

        # Ye badlein to dobara review chahiye; price/stock/discount par nahi.
        needs_review = (
            data['name'] != product.name
            or data['description'] != (product.description or '')
            or data['category'] != product.category
            or data['brand'] != product.brand
            or data['image'] is not None
        )

        product.name = data['name']
        product.description = data['description']
        product.category = data['category']
        product.brand = data['brand']
        product.unit = data['unit']
        product.original_price = data['price']
        product.price = data['price']
        product.discount_percentage = data['discount']

        if data['image']:
            product.image = data['image']
        else:
            # Product.save() har save par image dobara process karta hai (API call).
            # Image na badli ho to usay skip karo.
            product._image_processed = True

        if product.approval_status == 'rejected' or (
            needs_review and product.approval_status == 'approved' and not _auto_approve_products()
        ):
            product.approval_status = 'pending'
            product.rejection_reason = ''
            product.is_active = False
            resubmitted = True
        else:
            resubmitted = False

        pct = commission_percent(profile)
        cost = vendor_share(data['price'], data['discount'], pct)
        try:
            with transaction.atomic():
                product.save()
                reprice_open_batches(product, data['price'], data['discount'], pct)
                if data['stock'] > 0:
                    if not warehouse:
                        raise ValidationError('No warehouse is set for the shop')
                    _add_stock(product, warehouse, data['stock'], cost, data['price'])
        except ValidationError as exc:
            messages.error(request, f'❌ {_err_text(exc)}')
            return render(request, 'customer_portal/vendor/product_form.html',
                          _form_context(request, product=product, data=request.POST))
        except Exception:
            logger.exception("Vendor product edit error")
            messages.error(request, '❌ Could not update. Please try again')
            return redirect('vendor_product_edit', pk=pk)

        if resubmitted:
            messages.success(request, '✅ Updated. The change has been sent for admin review again.')
        else:
            messages.success(request, '✅ Product updated.')
        return redirect('vendor_dashboard')

    return render(request, 'customer_portal/vendor/product_form.html',
                  _form_context(request, product=product))


# ============================================
# 4b. CATEGORY / BRAND / UNIT  (+ button, admin form jaisa)
# ============================================

MASTER_MODELS = {'category': Category, 'brand': Brand, 'unit': Unit}
MASTER_LABELS = {'category': 'Category', 'brand': 'Brand', 'unit': 'Unit'}
MASTER_CREATE_LIMIT = 20          # ek vendor ghante mein itne naye naam bana sakta hai


@vendor_login_required
@flag_required('vendor_can_add_products', json=True)
@require_POST
def vendor_create_master(request, kind):
    """
    "+" button: naya Category/Brand/Unit banao. Agar wohi naam pehle se hai
    (capital/small ya extra spaces ka farq ignore) to naya nahi banta, mojooda wala wapas aata hai.
    """
    model = MASTER_MODELS.get(kind)
    if not model:
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
    label = MASTER_LABELS[kind]

    if not get_vendor_profile(request.user).is_approved:
        return JsonResponse({'success': False, 'message': 'Your account has not been approved yet.'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        payload = {}
    name = ' '.join(str(payload.get('name', '')).split())
    if len(name) < 2 or len(name) > 100:
        return JsonResponse({'success': False, 'message': f'{label} ka naam 2 se 100 characters ka likhein.'})

    existing = model.objects.filter(name__iexact=name).first()
    if existing:
        return JsonResponse({'success': True, 'id': existing.id, 'name': existing.name, 'existed': True})

    # Spam se bachao: ek vendor sirf limited naye naam bana sake.
    key = f'vendor_master_create_{request.user.id}'
    used = cache.get(key, 0)
    if used >= MASTER_CREATE_LIMIT:
        return JsonResponse({'success': False,
                             'message': 'The limit for creating new names has been reached. Please try again later.'})

    try:
        obj = model.objects.create(name=name)
    except IntegrityError:           # isi lamhe kisi aur ne wohi naam bana diya
        obj = model.objects.filter(name__iexact=name).first()
        if not obj:
            return JsonResponse({'success': False, 'message': 'Could not save. Please try again.'})
        return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name, 'existed': True})

    cache.set(key, used + 1, 3600)
    # Shop ke category/brand filter ki list 10 minute cache hoti hai; naya naam foran dikhane ke liye hata do.
    cache.delete('all_categories')
    cache.delete('all_brands')
    return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name, 'existed': False})


@vendor_login_required
@require_POST
def vendor_product_toggle(request, pk):
    """Approved product ko shop par show/hide karo (delete nahi, history bachi rahe)."""
    profile = get_vendor_profile(request.user)
    product = get_object_or_404(Product, pk=pk, vendor=profile.vendor)

    if product.approval_status != 'approved':
        messages.error(request, '❌ Only an approved product can be shown or hidden')
        return redirect('vendor_dashboard')

    Product.objects.filter(pk=product.pk).update(is_active=not product.is_active, hidden_by_suspend=False)
    messages.success(
        request,
        '👁️ The product is now visible in the shop' if not product.is_active
        else '🙈 Product shop se chhupa diya'
    )
    return redirect('vendor_dashboard')


# ============================================
# 5. STORE SETTINGS  (shop ki apni page: logo, hours, delivery fee ...)
# ============================================

def _parse_time(value):
    """'HH:MM' -> time ya None (khali). Ghalat format par ValueError."""
    value = (value or '').strip()
    if not value:
        return None
    h, m = value.split(':')[:2]
    return dtime(int(h), int(m))


def _parse_money(value, label, errors, maximum=Decimal('99999.99')):
    try:
        d = Decimal((value or '').strip() or '0')
        if d < 0 or d > maximum:
            raise InvalidOperation
        return d.quantize(Decimal('0.01'))
    except InvalidOperation:
        errors.append(f'{label} sahi likhein')
        return Decimal('0')


def _day_rows_for_form(profile, post=None):
    """Settings form ke 7 din: [{'i','name','closed','open','close'}] (galti par POST wali values wapas)."""
    rows = []
    saved = {r.weekday: r for r in profile.day_hours.all()}
    for i, name in enumerate(VendorProfile.DAY_NAMES):
        if post is not None:
            rows.append({'i': i, 'name': name, 'closed': bool(post.get(f'day_closed_{i}')),
                         'open': post.get(f'day_open_{i}', ''), 'close': post.get(f'day_close_{i}', '')})
        else:
            r = saved.get(i)
            rows.append({'i': i, 'name': name, 'closed': bool(r and r.is_closed),
                         'open': r.opens_at.strftime('%H:%M') if r and r.opens_at else '',
                         'close': r.closes_at.strftime('%H:%M') if r and r.closes_at else ''})
    return rows


@vendor_login_required
def vendor_store_settings(request):
    profile = get_vendor_profile(request.user)

    if request.method == 'POST':
        post, errors = request.POST, []

        status = post.get('store_status', 'open')
        if status not in ('open', 'busy', 'closed'):
            status = 'open'

        description = post.get('store_description', '').strip()[:1000]
        store_category = StoreCategory.objects.filter(
            pk=post.get('store_category') or 0, is_active=True).first()

        try:
            opens_at, closes_at = _parse_time(post.get('opens_at')), _parse_time(post.get('closes_at'))
        except (ValueError, TypeError):
            opens_at = closes_at = None
            errors.append('Enter valid opening and closing times')
        if bool(opens_at) != bool(closes_at):
            errors.append('Opening aur closing dono time likhein (ya dono khali chhoden)')

        day_rows = {}
        for i, dname in enumerate(VendorProfile.DAY_NAMES):
            closed = bool(post.get(f'day_closed_{i}'))
            try:
                d_open, d_close = _parse_time(post.get(f'day_open_{i}')), _parse_time(post.get(f'day_close_{i}'))
            except (ValueError, TypeError):
                errors.append(f'{dname}: valid time likhein')
                continue
            if closed:
                day_rows[i] = (True, None, None)
            elif bool(d_open) != bool(d_close):
                errors.append(f'{dname}: opening aur closing dono likhein (ya dono khali chhoden)')
            elif d_open and d_close:
                day_rows[i] = (False, d_open, d_close)

        min_order = _parse_money(post.get('min_order_amount'), 'Minimum order', errors)
        fee = _parse_money(post.get('delivery_fee'), 'Delivery fee', errors)
        fee_per_km = _parse_money(post.get('fee_per_km'), 'Fee per km', errors)
        free_radius = _parse_money(post.get('free_radius_km'), 'Free radius (km)', errors)
        max_km_raw = (post.get('max_delivery_km') or '').strip()
        max_km = _parse_money(max_km_raw, 'Max delivery distance (km)', errors) if max_km_raw else None
        if max_km is not None and max_km <= 0:
            max_km = None
        if free_radius > 999 or (max_km is not None and max_km > 999):
            errors.append('The distance limit cannot be more than 999 km')
        free_radius = free_radius.quantize(Decimal('0.1'))
        max_km = max_km.quantize(Decimal('0.1')) if max_km is not None else None

        # Cuisines (zyada se zyada 3, sirf active)
        cuisine_ids = []
        for x in post.getlist('cuisines'):
            try:
                cuisine_ids.append(int(x))
            except (TypeError, ValueError):
                pass
        cuisines = list(Cuisine.objects.filter(pk__in=cuisine_ids, is_active=True))
        if len(cuisines) > 3:
            errors.append('You can choose at most 3 cuisines')

        try:
            t_min = int(post.get('delivery_time_min') or 30)
            t_max = int(post.get('delivery_time_max') or 45)
            if not (5 <= t_min <= 600 and 5 <= t_max <= 600) or t_min > t_max:
                raise ValueError
        except ValueError:
            t_min, t_max = profile.delivery_time_min, profile.delivery_time_max
            errors.append('Enter the delivery time in minutes (min must not be more than max)')

        raw_areas = _areas_from_post(post)
        area_list = VendorProfile.clean_areas(raw_areas)
        if len([x for x in raw_areas.replace('\n', ',').replace(';', ',').split(',') if x.strip()]) > VendorProfile.MAX_AREAS:
            errors.append(f'Zyada se zyada {VendorProfile.MAX_AREAS} areas likh sakte hain')

        hide_sold_out = bool(post.get('hide_sold_out'))
        low_raw = (post.get('low_stock_level') or '').strip()
        low_level = None
        if low_raw:
            try:
                low_level = int(low_raw)
                if not 1 <= low_level <= 10000:
                    raise ValueError
            except ValueError:
                low_level = profile.low_stock_level
                errors.append('Low-stock level must be a number from 1 to 10000 (or leave it empty)')
        auto_accept = bool(post.get('auto_accept'))
        try:
            auto_prep = int(post.get('auto_accept_prep_minutes') or profile.auto_accept_prep_minutes or 20)
            if not 1 <= auto_prep <= 600:
                raise ValueError
        except ValueError:
            auto_prep = profile.auto_accept_prep_minutes
            errors.append('Auto-accept prep time must be 1 to 600 minutes')

        logo, cover = request.FILES.get('logo'), request.FILES.get('cover_image')
        for f in (logo, cover):
            if f:
                err = _validate_image(f)
                if err:
                    errors.append(err)

        if errors:
            for e in errors:
                messages.error(request, f'❌ {e}')
        else:
            profile.store_status = status
            profile.store_description = description
            profile.store_category = store_category
            profile.opens_at, profile.closes_at = opens_at, closes_at
            profile.min_order_amount, profile.delivery_fee = min_order, fee
            profile.fee_per_km, profile.free_radius_km, profile.max_delivery_km = fee_per_km, free_radius, max_km
            profile.delivery_time_min, profile.delivery_time_max = t_min, t_max
            profile.auto_accept, profile.auto_accept_prep_minutes = auto_accept, auto_prep
            profile.hide_sold_out, profile.low_stock_level = hide_sold_out, low_level
            profile.delivery_areas = ', '.join(area_list)
            if logo:
                profile.logo = logo
            if cover:
                profile.cover_image = cover
            if post.get('remove_logo') and not logo:
                profile.logo = None
            if post.get('remove_cover') and not cover:
                profile.cover_image = None
            profile.save()
            profile.cuisines.set(cuisines)
            with transaction.atomic():
                profile.day_hours.all().delete()
                for wd, (closed, d_open, d_close) in day_rows.items():
                    VendorDayHours.objects.create(store=profile, weekday=wd, is_closed=closed,
                                                  opens_at=d_open, closes_at=d_close)
            messages.success(request, '✅ Store settings saved.')
            return redirect('vendor_store_settings')

    return render(request, 'customer_portal/vendor/store_settings.html', {
        'page_title': 'Store Settings',
        'profile': profile,
        'store_categories': StoreCategory.objects.filter(is_active=True),
        'cuisines': Cuisine.objects.filter(is_active=True),
        'my_cuisine_ids': set(profile.cuisines.values_list('id', flat=True)),
        'day_rows': _day_rows_for_form(profile, request.POST if request.method == 'POST' else None),
        'distance_fee_on': shop_flag('shop_distance_fee_enabled'),
        'cuisines_on': shop_flag('shop_cuisines_enabled'),
        'company_name': _company_name(),
        **_area_context(profile),
    })


# ============================================
# 6. ORDERS (Accept / Reject / Ready)
# ============================================

ORDER_TABS = {
    'new': ('Naye', ['pending']),
    'active': ('Chal rahe', ['confirmed', 'processing', 'ready']),
    'done': ('Mukammal', ['partially_delivered', 'delivered', 'invoiced', 'cancelled']),
}


def _vendor_orders(vendor):
    return SaleOrder.objects.filter(vendor=vendor)


@vendor_login_required
@flag_required('vendor_can_manage_orders')
def vendor_orders(request):
    profile = get_vendor_profile(request.user)
    vendor = profile.vendor
    store_orders.expire_if_due()

    tab = request.GET.get('tab', 'new')
    if tab not in ORDER_TABS:
        tab = 'new'

    base = _vendor_orders(vendor)
    counts = {key: base.filter(status__in=statuses).count() for key, (_, statuses) in ORDER_TABS.items()}

    qs = (base.filter(status__in=ORDER_TABS[tab][1])
          .select_related('customer').prefetch_related('items__product')
          .order_by('order_date' if tab == 'new' else '-order_date')[:100])

    # Privacy (Talabat jaisa): vendor ko customer ka phone/address sirf tab tak jab tak zaroorat ho.
    #   * active order: phone dikhta hai; address tab tak jab tak rider assign na ho (rider address le jata hai)
    #   * mukammal order: address nahi, phone masked; cancelled order ka phone 2 din tak (rejection ka message bhejne ke liye)
    from datetime import timedelta
    from django.utils import timezone
    final_statuses = set(ORDER_TABS['done'][1])
    orders = []
    for o in qs:
        items = list(o.items.all())
        delivery = DeliveryInfo.objects.filter(sale_order=o).select_related('rider').first()
        is_final = o.status in final_statuses
        try:
            recent = (timezone.now() - o.order_date) <= timedelta(days=2)
        except Exception:
            recent = False
        show_contact = (not is_final) or (o.status == 'cancelled' and recent)
        show_address = (not is_final) and not (delivery and delivery.rider_id)
        phone = o.customer.contact_number
        wa_action = {'confirmed': 'accept', 'ready': 'ready', 'delivered': 'delivered', 'cancelled': 'reject'}.get(o.status)
        wa_url = None
        if phone and wa_action and show_contact:
            wa_url = store_orders.whatsapp_link(phone, store_orders.customer_whatsapp_text(o, wa_action))
        orders.append({
            'order': o,
            'items': items,
            'subtotal': o.total_after_discount(),
            'total': store_orders.order_payable_total(o),
            'cash_due': store_orders.order_cash_due(o),
            'wallet_paid': o.wallet_paid,
            'wa_url': wa_url,
            'call_phone': phone if show_contact else None,
            'show_contact': show_contact,
            'show_address': show_address,
            'is_cod': (o.payment_method or 'cod') == 'cod',
            'delivery': delivery,
            'accept_deadline': store_orders.accept_deadline(o),
        })

    return render(request, 'customer_portal/vendor/orders.html', {
        'riders': list(RiderProfile.objects.filter(is_active=True, approval_status='approved')),
        'page_title': 'Orders',
        'profile': profile,
        'orders': orders,
        'tab': tab,
        'tabs': [(k, v[0], counts[k]) for k, v in ORDER_TABS.items()],
        'new_count': counts['new'],
        'reject_reasons': store_orders.REJECT_REASONS,
        'company_name': _company_name(),
    })


@vendor_login_required
@flag_required('vendor_can_manage_orders')
@require_POST
def vendor_order_action(request, pk, action):
    """action: accept | reject | ready | delivered."""
    vendor = get_vendor_profile(request.user).vendor
    tab = request.POST.get('tab', 'new')
    back = f"{reverse('vendor_orders')}?tab={tab if tab in ORDER_TABS else 'new'}"

    if not get_vendor_profile(request.user).is_approved:
        messages.error(request, '❌ You can handle orders only after your account is approved.')
        return redirect(back)

    try:
        with transaction.atomic():
            # sirf apne store ka order (kisi aur vendor ka order chhoone ki koshish 404 degi)
            order = get_object_or_404(
                SaleOrder.objects.select_for_update(), pk=pk, vendor=vendor)

            prep = None
            if action == 'accept':
                raw = request.POST.get('prep_minutes', '').strip()
                if raw:
                    try:
                        prep = int(raw)
                    except ValueError:
                        raise store_orders.OrderActionError('Enter the preparation time in minutes.')
                    if not 1 <= prep <= 600:
                        raise store_orders.OrderActionError('Tayyari ka time 1 se 600 minute ke beech likhein.')

            store_orders.apply_vendor_action(
                order, action, user=request.user, prep_minutes=prep,
                reason_code=request.POST.get('reason_code', ''),
                reason_note=request.POST.get('reason_note', ''),
            )
    except store_orders.OrderActionError as exc:
        messages.error(request, f'❌ {exc}')
        return redirect(back)

    done = {
        'accept': f'✅ Order #{order.order_no} qubool kar liya.',
        'reject': f'❌ Order #{order.order_no} reject kar diya. Customer ko wajah bata di gayi.',
        'ready': f'📦 Order #{order.order_no} tayyar hai.',
        'delivered': f'🎉 Order #{order.order_no} deliver ho gaya. Mukammal tab mein dekh sakte hain.',
    }[action]
    messages.success(request, done)
    # accept ke baad order "Chal rahe" mein chala jata hai
    next_tab = {'accept': 'active', 'ready': 'active', 'reject': 'done', 'delivered': 'done'}[action]
    return redirect(f"{reverse('vendor_orders')}?tab={next_tab}")


@vendor_login_required
@flag_required('vendor_can_manage_orders', json=True)
def vendor_orders_poll(request):
    """Orders page har 30 second mein poochta hai: kitne naye order hain (naya aane par beep)."""
    vendor = get_vendor_profile(request.user).vendor
    store_orders.expire_if_due()
    new = _vendor_orders(vendor).filter(status='pending')
    latest = new.order_by('-id').values_list('id', flat=True).first() or 0
    return JsonResponse({'new': new.count(), 'latest_id': latest})
