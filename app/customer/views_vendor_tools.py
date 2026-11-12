"""Vendor portal: Busy mode, Sales reports, Offers (discount).

- Busy mode: vendor N minute ke liye naye orders rok deta hai; waqt poora hone par store khud khul jata hai.
- Reports: kitne order, bikri, top products, kon se ghante busy; CSV download.
- Offers: poore store / ek category / chune hue products par discount. Product ka discount_percentage hi
  badalta hai (isi se customer ki price banti hai), aur commission ka hisaab product edit jaisa hi rehta hai:
  discount vendor khud bardasht karta hai (reprice_open_batches).
"""
import csv
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import Category, Product, SaleOrder, SaleOrderItem
from ..shop_flags import flag_required
from ..vendor_commission import commission_percent, reprice_open_batches
from .views_vendor_menu import vendor_categories

logger = logging.getLogger(__name__)

PAUSE_CHOICES = (15, 30, 60, 120)
DONE_STATUSES = ['delivered', 'invoiced', 'partially_delivered']
MAX_DISCOUNT = Decimal('90')
MAX_RANGE_DAYS = 92
LINE_TOTAL = ExpressionWrapper(F('qty') * F('price'), output_field=DecimalField(max_digits=18, decimal_places=2))


# ============================================
# BUSY MODE
# ============================================

@require_POST
@vendor_login_required
def vendor_pause(request):
    profile = request.user.vendor_profile
    try:
        minutes = int(request.POST.get('minutes', 0))
    except (TypeError, ValueError):
        minutes = -1
    if minutes == 0:
        profile.paused_until = None
        profile.save(update_fields=['paused_until'])
        messages.success(request, '✅ Busy mode is off. Customers can order now.')
    elif minutes in PAUSE_CHOICES:
        profile.paused_until = timezone.now() + timedelta(minutes=minutes)
        profile.save(update_fields=['paused_until'])
        messages.success(request, f'⏸️ Busy mode: new orders paused for {minutes} minutes '
                                  f'({profile.paused_until_text} par khud khul jayega).')
    else:
        messages.error(request, '❌ Invalid time')
    return redirect('vendor_orders' if request.POST.get('next') == 'orders' else 'vendor_dashboard')


# ============================================
# REPORTS
# ============================================

def _day_start(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _parse_date(text):
    try:
        return datetime.strptime((text or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _report_range(request):
    today = timezone.localdate()
    key = request.GET.get('range', '7d')
    if key == 'today':
        start = end = today
    elif key == '30d':
        start, end = today - timedelta(days=29), today
    elif key == 'month':
        start, end = today.replace(day=1), today
    elif key == 'custom':
        start = _parse_date(request.GET.get('from')) or today - timedelta(days=6)
        end = _parse_date(request.GET.get('to')) or today
        if start > end:
            start, end = end, start
        end = min(end, today)
        start = max(start, end - timedelta(days=MAX_RANGE_DAYS - 1))
    else:
        key = '7d'
        start, end = today - timedelta(days=6), today
    return key, start, end


def _hour_label(h):
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def _safe_cell(v):
    """CSV mein Excel formula (=,+,-,@) se bachao."""
    v = str(v)
    return "'" + v if v[:1] in ('=', '+', '-', '@') else v


@vendor_login_required
def vendor_reports(request):
    profile = request.user.vendor_profile
    vendor = profile.vendor
    key, start, end = _report_range(request)
    a, b = _day_start(start), _day_start(end + timedelta(days=1))

    orders = SaleOrder.objects.filter(vendor=vendor, order_date__gte=a, order_date__lt=b)
    done = orders.filter(status__in=DONE_STATUSES)
    total_orders = orders.count()
    cancelled = orders.filter(status='cancelled').count()
    delivered = done.count()
    active = total_orders - cancelled - delivered

    items = SaleOrderItem.objects.filter(order__in=done)
    gross = items.aggregate(t=Sum(LINE_TOTAL))['t'] or Decimal('0')
    discounts = done.aggregate(t=Sum('discount_value'))['t'] or Decimal('0')
    sales = (Decimal(gross) - Decimal(discounts)).quantize(Decimal('0.01'))
    pct = commission_percent(profile)
    commission = (sales * pct / Decimal('100')).quantize(Decimal('0.01'))
    avg = (sales / delivered).quantize(Decimal('0.01')) if delivered else Decimal('0.00')
    cancel_rate = round(cancelled * 100 / total_orders) if total_orders else 0

    sort = 'revenue' if request.GET.get('top') == 'revenue' else 'qty'
    top_qs = (items.values('product_id', 'product__name')
              .annotate(qty=Sum('qty'), revenue=Sum(LINE_TOTAL))
              .order_by('-revenue' if sort == 'revenue' else '-qty', 'product__name'))

    # Din ke hisaab se bikri (31 din tak roz; us se lamba ho to hafte ke hisaab se)
    span = (end - start).days + 1
    weekly = span > 31
    buckets = {}
    for row in items.annotate(day=TruncDate('order__order_date')).values('day').annotate(
            sales=Sum(LINE_TOTAL)):
        d = row['day']
        k = d - timedelta(days=d.weekday()) if weekly else d
        buckets[k] = buckets.get(k, Decimal('0')) + Decimal(row['sales'] or 0)
    order_counts = {}
    for row in done.annotate(day=TruncDate('order_date')).values('day').annotate(n=Count('id')):
        d = row['day']
        k = d - timedelta(days=d.weekday()) if weekly else d
        order_counts[k] = order_counts.get(k, 0) + row['n']
    series, d = [], start - timedelta(days=start.weekday()) if weekly else start
    step = timedelta(days=7 if weekly else 1)
    while d <= end:
        series.append({'day': d, 'sales': buckets.get(d, Decimal('0')), 'orders': order_counts.get(d, 0)})
        d += step
    top_day = max((r['sales'] for r in series), default=Decimal('0'))
    for r in series:
        r['pct'] = int(r['sales'] * 100 / top_day) if top_day else 0

    hours = (orders.exclude(status='cancelled').annotate(h=ExtractHour('order_date'))
             .values('h').annotate(n=Count('id')).order_by('-n', 'h')[:3])
    busy_hours = [{'label': _hour_label(r['h']), 'n': r['n']} for r in hours]

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="sales_{start}_{end}.csv"'
        resp.write('\ufeff')
        w = csv.writer(resp)
        w.writerow(['Report', f'{start} to {end}'])
        w.writerow(['Orders', total_orders, 'Delivered', delivered, 'Cancelled', cancelled])
        w.writerow(['Sales', sales, 'Avg order', avg])
        w.writerow([])
        w.writerow(['Product', 'Qty', 'Sales'])
        for r in top_qs:
            w.writerow([_safe_cell(r['product__name']), r['qty'], r['revenue']])
        w.writerow([])
        w.writerow(['Week starting' if weekly else 'Day', 'Orders', 'Sales'])
        for r in series:
            w.writerow([r['day'], r['orders'], r['sales']])
        return resp

    return render(request, 'customer_portal/vendor/reports.html', {
        'profile': profile,
        'range_key': key, 'start': start, 'end': end,
        'total_orders': total_orders, 'delivered': delivered, 'cancelled': cancelled, 'active': active,
        'cancel_rate': cancel_rate,
        'sales': sales, 'avg': avg, 'commission': commission, 'pct': pct.normalize(),
        'earn': (sales - commission).quantize(Decimal('0.01')),
        'top': list(top_qs[:10]), 'top_sort': sort,
        'series': series, 'weekly': weekly,
        'busy_hours': busy_hours,
    })


# ============================================
# OFFERS (discount)
# ============================================

def _apply_discount(product, discount, pct):
    """Product par discount lagao / hatao (discount=0). Price ka hisaab product edit jaisa."""
    if product.discount_percentage and product.discount_percentage > 0 and (product.original_price or 0) > 0:
        base = product.original_price
    else:
        base = product.price
    product.original_price = base
    product.price = base
    product.discount_percentage = discount
    product._image_processed = True        # image dobara process (API call) na ho
    product.save()
    reprice_open_batches(product, base, discount, pct)


@vendor_login_required
@flag_required('vendor_can_add_products', redirect_to='vendor_dashboard')
def vendor_offers(request):
    profile = request.user.vendor_profile
    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')
    vendor = profile.vendor
    pct = commission_percent(profile)

    if request.method == 'POST':
        try:
            _offers_post(request, vendor, pct)
        except Exception:
            logger.exception('Vendor offers error')
            messages.error(request, '❌ Something went wrong. Please try again')
        return redirect('vendor_offers')

    products = list(Product.objects.filter(vendor=vendor).select_related('category').order_by('name'))
    on_offer = [p for p in products if p.discount_percentage and p.discount_percentage > 0]
    return render(request, 'customer_portal/vendor/offers.html', {
        'profile': profile,
        'products': products,
        'on_offer': on_offer,
        'categories': vendor_categories(profile),
        'max_discount': int(MAX_DISCOUNT),
    })


def _scope_products(request, vendor):
    post = request.POST
    qs = Product.objects.filter(vendor=vendor)
    scope = post.get('scope', 'all')
    if scope == 'category':
        try:
            qs = qs.filter(category_id=int(post.get('category_id')))
        except (TypeError, ValueError):
            return None, 'Category chunein'
    elif scope == 'selected':
        ids = []
        for v in post.getlist('product_ids'):
            try:
                ids.append(int(v))
            except ValueError:
                continue
        if not ids:
            return None, 'Kam az kam ek product chunein'
        qs = qs.filter(id__in=ids)
    return list(qs), None


def _offers_post(request, vendor, pct):
    post = request.POST
    action = post.get('action')

    if action == 'clear_one':
        product = Product.objects.filter(vendor=vendor, pk=post.get('product_id')).first()
        if product:
            with transaction.atomic():
                _apply_discount(product, Decimal('0'), pct)
            messages.success(request, f'✅ Offer ended for "{product.name}".')
        return

    if action in ('apply', 'clear_scope'):
        products, err = _scope_products(request, vendor)
        if err:
            messages.error(request, f'❌ {err}')
            return
        if not products:
            messages.error(request, '❌ No products found in this')
            return
        if action == 'clear_scope':
            discount = Decimal('0')
        else:
            try:
                discount = Decimal((post.get('percent') or '').strip())
            except (InvalidOperation, ValueError):
                discount = Decimal('0')
            if discount < 1 or discount > MAX_DISCOUNT:
                messages.error(request, f'❌ Enter a discount between 1 and {int(MAX_DISCOUNT)} percent')
                return
        with transaction.atomic():
            for p in products:
                _apply_discount(p, discount, pct)
        if discount:
            messages.success(request, f'🏷️ {discount.normalize()}% discount applied to {len(products)} product(s).')
        else:
            messages.success(request, f'✅ Offer ended for {len(products)} product(s).')
