"""Vendor portal: branches. Sirf owner (main store ka login).

Branch = alag store (alag products, orders, payouts, store page). Customer ko ye apne naam
"Business - Branch" se alag store ki tarah dikhti hai. Owner ek click se branch par switch karta hai.

- vendor_branches       : /shop/vendor/branches/  (list + nayi branch)
- vendor_branch_action  : switch (branch ya main)
"""
import logging

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import (
    Product, ProductOption, ProductOptionGroup, StoreMenuSection, Vendor, VendorProfile,
)
from .views_customer_auth import is_valid_phone, normalize_phone
from .vendor_access import SESSION_KEY, get_vendor_profile

logger = logging.getLogger(__name__)

MAX_BRANCHES = 20

# Main store se naye branch me copy hone wali settings (taake branch foran chalne ke qabil ho)
COPY_FIELDS = (
    'store_category', 'store_description', 'logo', 'cover_image', 'commission_percent',
    'payout_method', 'payout_account_title', 'payout_account_no',
    'min_order_amount', 'delivery_fee', 'fee_per_km', 'free_radius_km', 'max_delivery_km',
    'delivery_time_min', 'delivery_time_max', 'opens_at', 'closes_at',
    'hide_sold_out', 'low_stock_level',
)


def _owner(request):
    """Main store ka profile (branch ke andar hone par bhi)."""
    return request.user.vendor_profile


def _create_branch(request, owner):
    post = request.POST
    branch_name = ' '.join(post.get('branch_name', '').split())[:60]
    phone_raw = post.get('phone', '').strip()[:20]
    city = post.get('city', '').strip()[:100] or owner.city
    address = post.get('address', '').strip()[:300]
    delivery_areas = post.get('delivery_areas', '').strip()[:1000]

    if not owner.is_approved:
        return '⏳ Branch banane ke liye pehle apna account approve hona chahiye'
    if len(branch_name) < 2:
        return '❌ Branch ka naam likhein (jaise: Gulberg)'
    if len(address) < 10:
        return '❌ Branch ka poora address likhein'
    if owner.branches.count() >= MAX_BRANCHES:
        return f'❌ Zyada se zyada {MAX_BRANCHES} branches ban sakti hain'
    if owner.branches.filter(branch_name__iexact=branch_name).exists():
        return '❌ Is naam ki branch pehle se hai'

    phone = None
    if phone_raw:
        if not is_valid_phone(phone_raw):
            return '❌ Sahi phone number likhein (ya khali chorden)'
        phone = normalize_phone(phone_raw)
        from ..models import VendorStaff
        if Vendor.objects.filter(contact_number=phone).exists() or VendorStaff.objects.filter(phone=phone).exists():
            return '❌ Ye phone pehle se kisi account me hai'

    full_name = f'{owner.business_name} - {branch_name}'[:100]
    with transaction.atomic():
        base, n = f'vbranch_{owner.pk}', 1
        username = base
        while User.objects.filter(username=username).exists():
            n += 1
            username = f'{base}_{n}'
        # Branch ka apna login nahi: password unusable, owner switch karke chalata hai
        user = User.objects.create_user(username=username, password=None)
        user.set_unusable_password()
        user.save(update_fields=['password'])

        vendor = Vendor.objects.create(name=full_name, contact_number=phone,
                                       address=f'{address}, {city}')
        data = {f: getattr(owner, f) for f in COPY_FIELDS}
        branch = VendorProfile.objects.create(
            vendor=vendor, user=user, parent=owner, branch_name=branch_name,
            business_name=full_name, city=city, delivery_areas=delivery_areas,
            is_approved=True, approved_at=now(), **data)
        branch.cuisines.set(owner.cuisines.all())
        from ..models import VendorDayHours
        for r in owner.day_hours.all():
            VendorDayHours.objects.create(store=branch, weekday=r.weekday, is_closed=r.is_closed,
                                          opens_at=r.opens_at, closes_at=r.closes_at)
    messages.success(request, f'✅ Branch "{branch_name}" ban gayi. Switch karke products add karein.')
    return None


@vendor_login_required
def vendor_branches(request):
    owner = _owner(request)
    if request.method == 'POST':
        try:
            err = _create_branch(request, owner)
            if err:
                messages.error(request, err)
        except Exception:
            logger.exception('Vendor branch create error')
            messages.error(request, '❌ Something went wrong. Please try again')
        return redirect('vendor_branches')

    return render(request, 'customer_portal/vendor/branches.html', {
        'owner': owner,
        'branches': owner.branches.select_related('vendor'),
        'active': get_vendor_profile(request.user),
        'max_branches': MAX_BRANCHES,
    })


def _blockers(branch):
    """Branch ki wo history jis ki wajah se delete nahi ho sakti (orders, payouts, hisaab...)."""
    names = []
    for rel in Vendor._meta.related_objects:
        model = rel.related_model
        if model in (VendorProfile, Product):
            continue
        try:
            has = model._default_manager.filter(**{rel.field.name: branch.vendor}).exists()
        except Exception:
            has = True      # shak ho to delete nahi
        if has:
            names.append(str(model._meta.verbose_name_plural))
    return names


def _delete_branch(request, owner, branch):
    if not request.user.check_password(request.POST.get('password', '')):
        return '❌ Password galat hai. Delete karne ke liye apna password likhein.'
    blockers = _blockers(branch)
    if blockers:
        return ('❌ Is branch ka record hai (' + ', '.join(sorted(set(blockers))[:4]) + ') is liye delete nahi ho sakti. '
                'Switch karke Store settings me store ko "Closed" kar dein.')
    try:
        with transaction.atomic():
            from ..models import VendorStaff
            staff_users = []
            for rec in VendorStaff.objects.filter(store=branch).prefetch_related('extra_stores'):
                others = [p for p in rec.extra_stores.all() if p.pk != branch.pk]
                if others:      # staff aur stores par bhi kaam karta hai: us ka login rahega
                    rec.store = others[0]
                    rec.save(update_fields=['store'])
                    rec.extra_stores.remove(others[0])
                else:
                    staff_users.append(rec.user)
            Product.objects.filter(vendor=branch.vendor).delete()
            user, vendor, name = branch.user, branch.vendor, branch.branch_name
            vendor.delete()          # profile, staff records, deals, sponsorships saath chale jate hain
            user.delete()
            for u in staff_users:
                u.delete()
    except (ProtectedError, IntegrityError):
        logger.exception('Branch delete blocked')
        return '❌ Is branch ke products ka record dusri jagah use ho raha hai, is liye delete nahi ho saki.'
    if request.session.get(SESSION_KEY) == branch.pk:
        request.session.pop(SESSION_KEY, None)
    messages.success(request, f'🗑️ Branch "{name}" aur uske products delete ho gaye.')
    return None


@vendor_login_required
@require_POST
def vendor_branch_action(request, pk, action):
    owner = _owner(request)
    if action == 'switch':
        if pk == 0:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, f'🏪 Ab aap "{owner.business_name}" (main store) chala rahe hain.')
        else:
            branch = get_object_or_404(VendorProfile, pk=pk, parent=owner)
            request.session[SESSION_KEY] = branch.pk
            messages.success(request, f'🏪 Ab aap "{branch.business_name}" chala rahe hain.')
        return redirect('vendor_dashboard')
    if action == 'delete' and pk:
        branch = get_object_or_404(VendorProfile, pk=pk, parent=owner)
        try:
            err = _delete_branch(request, owner, branch)
        except Exception:
            logger.exception('Vendor branch delete error')
            err = '❌ Something went wrong. Please try again'
        if err:
            messages.error(request, err)
        return redirect('vendor_branches')
    messages.error(request, '❌ Galat action.')
    return redirect('vendor_branches')


# ============================================
# Products ek store se doosre store me copy
# ============================================

def _copy_options(src_product, new_product):
    """Variants/add-ons (groups + options, sub-choices samet) copy."""
    option_map = {}
    group_pairs = []
    for g in src_product.option_groups.all().prefetch_related('options'):
        ng = ProductOptionGroup.objects.create(
            product=new_product, name=g.name, kind=g.kind, is_required=g.is_required,
            max_select=g.max_select, sort_order=g.sort_order, is_active=g.is_active)
        group_pairs.append((g, ng))
        for o in g.options.all():
            no = ProductOption.objects.create(
                group=ng, name=o.name, extra_price=o.extra_price,
                is_available=o.is_available, sort_order=o.sort_order)
            option_map[o.pk] = no
    for g, ng in group_pairs:
        if g.parent_option_id and g.parent_option_id in option_map:
            ng.parent_option = option_map[g.parent_option_id]
            ng.save(update_fields=['parent_option'])


def _copy_products(request, src, dst, product_ids, with_options, stock_each):
    from .vendor_commission import commission_percent, vendor_share
    from .views_vendor_portal import _add_stock, _auto_approve_products, _stock_warehouse
    live = _auto_approve_products()
    warehouse = _stock_warehouse()
    existing = {n.lower() for n in Product.objects.filter(vendor=dst.vendor).values_list('name', flat=True)}
    copied = skipped = failed = 0
    cat_ids = set()
    qs = (Product.objects.filter(vendor=src.vendor, pk__in=product_ids)
          .exclude(approval_status='rejected').order_by('name'))
    for sp in qs:
        if sp.name.lower() in existing:
            skipped += 1
            continue
        base = sp.original_price if sp.original_price and sp.original_price > 0 else sp.price
        try:
            with transaction.atomic():
                p = Product(
                    name=sp.name, description=sp.description, category=sp.category, brand=sp.brand,
                    unit=sp.unit, types=sp.types, original_price=base, price=base,
                    discount_percentage=sp.discount_percentage,
                    low_stock_threshold=sp.low_stock_threshold, is_popular=sp.is_popular,
                    vendor=dst.vendor, created_by=request.user,
                    approval_status='approved' if live else 'pending', is_active=live,
                )
                if sp.image:
                    p.image = sp.image.name          # wahi file, dobara compress nahi
                    p._image_processed = True
                p.save()
                if with_options:
                    _copy_options(sp, p)
                if stock_each > 0:
                    cost = vendor_share(base, sp.discount_percentage, commission_percent(dst))
                    _add_stock(p, warehouse, stock_each, cost, base)
            existing.add(sp.name.lower())
            copied += 1
            if sp.category_id:
                cat_ids.add(sp.category_id)
        except Exception:
            logger.exception('Branch product copy failed: %s', sp.pk)
            failed += 1
    # Menu sections ki tarteeb bhi (jo dst me pehle se na ho)
    for row in StoreMenuSection.objects.filter(store=src, category_id__in=cat_ids):
        StoreMenuSection.objects.get_or_create(store=dst, category_id=row.category_id,
                                               defaults={'sort_order': row.sort_order})
    return copied, skipped, failed


@vendor_login_required
def vendor_branch_copy(request):
    owner = _owner(request)
    stores = [owner] + list(owner.branches.all())
    by_id = {s.pk: s for s in stores}

    def pick(value):
        try:
            return by_id.get(int(value))
        except (TypeError, ValueError):
            return None

    if request.method == 'POST':
        src, dst = pick(request.POST.get('src')), pick(request.POST.get('dst'))
        if not src or not dst or src.pk == dst.pk:
            messages.error(request, '❌ Do alag alag stores chunein')
            return redirect('vendor_branch_copy')
        ids = [i for i in request.POST.getlist('product') if i.isdigit()]
        if not ids:
            messages.error(request, '❌ Kam az kam ek product chunein')
            return redirect(f"{request.path}?src={src.pk}&dst={dst.pk}")
        try:
            stock_each = max(0, min(100000, int(request.POST.get('stock') or 0)))
        except ValueError:
            stock_each = 0
        copied, skipped, failed = _copy_products(
            request, src, dst, ids, bool(request.POST.get('with_options')), stock_each)
        msg = f'✅ {copied} product(s) "{dst.business_name}" me copy ho gaye.'
        if skipped:
            msg += f' {skipped} pehle se maujood the (chhor diye).'
        if failed:
            msg += f' {failed} copy nahi ho sake.'
        (messages.success if copied else messages.warning)(request, msg)
        return redirect('vendor_branches')

    src, dst = pick(request.GET.get('src')), pick(request.GET.get('dst'))
    products = []
    if src and dst and src.pk != dst.pk:
        have = {n.lower() for n in Product.objects.filter(vendor=dst.vendor).values_list('name', flat=True)}
        for p in (Product.objects.filter(vendor=src.vendor).exclude(approval_status='rejected')
                  .select_related('category').order_by('name')):
            p.already = p.name.lower() in have
            products.append(p)
    return render(request, 'customer_portal/vendor/branch_copy.html', {
        'stores': stores, 'src': src, 'dst': dst, 'products': products,
    })
