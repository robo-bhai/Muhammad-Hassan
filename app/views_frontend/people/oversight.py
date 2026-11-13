"""Frontend views: admin overview dashboard + vendor performance report (nigrani ek jagah)."""
import csv
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from ...models import (AccountActionLog, BlockedIdentity, CompanyInfo, CustomerProfile, DeliveryInfo,
                       OrderDispute, OrderReview, Product, SaleOrder, SaleOrderItem, VendorProfile)
from ...security.permissions import perm_required
from ...utils.vendor_perf_rules import flags as perf_flags, fmt_minutes, percent

PERIODS = [(7, 'Pichhle 7 din'), (30, 'Pichhle 30 din'), (90, 'Pichhle 90 din'), (0, 'Sara waqt')]
SORTS = {   # key: (row field, sabse bura pehle -> descending?)
    'orders': ('orders', True), 'cancel': ('cancel_rate', True), 'rating': ('rating', False),
    'delivery': ('delivery_min', True), 'disputes': ('disputes', True), 'sales': ('sales', True),
}


def _minutes(td):
    return round(td.total_seconds() / 60.0, 1) if td is not None else None


def vendor_performance_rows(days=30):
    """Har vendor profile ki performance (days=0 -> sara waqt). Wapas: dict ki list."""
    start = timezone.now() - timedelta(days=days) if days else None
    dur = lambda a, b: ExpressionWrapper(F(a) - F(b), output_field=DurationField())

    orders = SaleOrder.objects.filter(vendor__isnull=False)
    items = SaleOrderItem.objects.filter(order__vendor__isnull=False,
                                         order__status__in=('delivered', 'invoiced'))
    deliveries = DeliveryInfo.objects.filter(sale_order__vendor__isnull=False, delivered_at__isnull=False)
    reviews = OrderReview.objects.filter(vendor__isnull=False, vendor_rating__isnull=False)
    disputes = OrderDispute.objects.filter(vendor__isnull=False)
    if start:
        orders = orders.filter(created_at__gte=start)
        items = items.filter(order__created_at__gte=start)
        deliveries = deliveries.filter(sale_order__created_at__gte=start)
        reviews = reviews.filter(created_at__gte=start)
        disputes = disputes.filter(created_at__gte=start)

    base = {r['vendor_id']: r for r in orders.order_by().values('vendor_id').annotate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status__in=('delivered', 'invoiced'))),
        cancelled=Count('id', filter=Q(status='cancelled')),
        rejected=Count('id', filter=Q(status='cancelled') & ~Q(reject_reason='')),
        resp=Avg(dur('vendor_responded_at', 'created_at'), filter=Q(vendor_responded_at__isnull=False)),
    )}
    sales = {r['order__vendor_id']: r['t'] for r in
             items.order_by().values('order__vendor_id').annotate(t=Sum('total_amt'))}
    deliv = {r['sale_order__vendor_id']: r['avg'] for r in
             deliveries.order_by().values('sale_order__vendor_id')
             .annotate(avg=Avg(dur('delivered_at', 'sale_order__created_at')))}
    rated = {r['vendor_id']: r for r in
             reviews.order_by().values('vendor_id').annotate(avg=Avg('vendor_rating'), n=Count('id'))}
    disp = {r['vendor_id']: r['n'] for r in
            disputes.order_by().values('vendor_id').annotate(n=Count('id'))}

    rows = []
    for p in VendorProfile.objects.select_related('vendor'):
        b = base.get(p.vendor_id, {})
        rv = rated.get(p.vendor_id)
        total = b.get('total', 0)
        row = {
            'vendor_id': p.vendor_id, 'name': p.business_name, 'city': p.city,
            'status': 'approved' if p.is_approved else ('suspended' if p.approved_at else 'pending'),
            'orders': total, 'delivered': b.get('delivered', 0),
            'cancelled': b.get('cancelled', 0), 'rejected': b.get('rejected', 0),
            'cancel_rate': percent(b.get('cancelled', 0), total),
            'response_min': _minutes(b.get('resp')),
            'delivery_min': _minutes(deliv.get(p.vendor_id)),
            'rating': round(float(rv['avg']), 1) if rv and rv['avg'] else None,
            'rating_n': rv['n'] if rv else 0,
            'disputes': disp.get(p.vendor_id, 0),
            'sales': sales.get(p.vendor_id) or 0,
        }
        row['flags'] = perf_flags(row)
        row['delivery_txt'] = fmt_minutes(row['delivery_min'])
        row['response_txt'] = fmt_minutes(row['response_min'])
        rows.append(row)
    return rows


@login_required
@perm_required('view_vendors')
def vendor_performance(request):
    try:
        days = int(request.GET.get('days', 30))
    except ValueError:
        days = 30
    if days not in dict(PERIODS):
        days = 30
    sort = request.GET.get('sort', 'orders')
    if sort not in SORTS:
        sort = 'orders'
    only_flagged = request.GET.get('flagged') == '1'
    # Form bheja gaya ho ('f') to checkbox ka jawab maano, warna pehli dafa default = bina orders wale chhupao
    only_active = (request.GET.get('hide_empty') == '1') if 'f' in request.GET else True

    rows = vendor_performance_rows(days)
    if only_active:
        rows = [r for r in rows if r['orders'] or r['disputes']]
    if only_flagged:
        rows = [r for r in rows if r['flags']]
    field, desc = SORTS[sort]
    have = [r for r in rows if r[field] is not None]
    none = [r for r in rows if r[field] is None]
    rows = sorted(have, key=lambda r: r[field], reverse=desc) + none

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="vendor_performance.csv"'
        resp.write('\ufeff')
        w = csv.writer(resp)
        w.writerow(['Vendor', 'City', 'Status', 'Orders', 'Delivered', 'Cancelled', 'Cancel %', 'Rejected by vendor',
                    'Avg response (min)', 'Avg delivery (min)', 'Rating', 'Ratings', 'Disputes', 'Sales (Rs)', 'Flags'])
        for r in rows:
            w.writerow([r['name'], r['city'], r['status'], r['orders'], r['delivered'], r['cancelled'],
                        r['cancel_rate'] if r['cancel_rate'] is not None else '', r['rejected'],
                        r['response_min'] if r['response_min'] is not None else '',
                        r['delivery_min'] if r['delivery_min'] is not None else '',
                        r['rating'] if r['rating'] is not None else '', r['rating_n'], r['disputes'],
                        r['sales'], '; '.join(r['flags'])])
        return resp

    return render(request, 'oversight/vendor_performance.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'rows': rows, 'days': days, 'periods': PERIODS, 'sort': sort, 'sorts': list(SORTS),
        'flagged': only_flagged, 'hide_empty': only_active,
        'flagged_count': sum(1 for r in rows if r['flags']),
    })


@login_required
@perm_required('view_vendors')
def oversight_dashboard(request):
    """Aaj ki tasveer: naye vendors/customers, suspended, pending approvals, open disputes."""
    today = timezone.localdate()
    open_disputes = OrderDispute.objects.filter(status__in=OrderDispute.OPEN_STATUSES)
    pending_accounts = VendorProfile.objects.filter(is_approved=False, approved_at__isnull=True)
    today_orders = SaleOrder.objects.filter(vendor__isnull=False, created_at__date=today)

    cards = {
        'new_vendors': VendorProfile.objects.filter(created_at__date=today).count(),
        'new_customers': CustomerProfile.objects.filter(created_at__date=today).count(),
        'orders_today': today_orders.count(),
        'cancelled_today': today_orders.filter(status='cancelled').count(),
        'pending_accounts': pending_accounts.count(),
        'pending_products': Product.objects.filter(vendor__isnull=False, approval_status='pending').count(),
        'suspended_customers': CustomerProfile.objects.filter(is_suspended=True).count(),
        'suspended_vendors': VendorProfile.objects.filter(is_approved=False, approved_at__isnull=False).count(),
        'open_disputes': open_disputes.count(),
        'blocked': BlockedIdentity.objects.filter(is_active=True).count(),
    }
    flagged = [r for r in vendor_performance_rows(30) if r['flags']]
    flagged.sort(key=lambda r: len(r['flags']), reverse=True)

    return render(request, 'oversight/dashboard.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'today': today, 'cards': cards,
        'pending_list': pending_accounts.select_related('vendor').order_by('-created_at')[:5],
        'dispute_list': open_disputes.select_related('customer', 'vendor').order_by('created_at')[:5],
        'history': AccountActionLog.objects.all()[:6],
        'flagged': flagged[:5], 'flagged_total': len(flagged),
    })
