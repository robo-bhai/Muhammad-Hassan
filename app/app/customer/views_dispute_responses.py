"""Vendor aur rider ka dispute par jawab: list + detail (jawab form).

Privacy: customer ka sirf pehla naam dikhta hai, phone/address nahi.
Har party sirf apne hi disputes dekh sakti hai (vendor = apna store, rider = apni deliveries).
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from ..decorators import vendor_login_required
from . import disputes as logic
from . import store_orders
from .views_rider_portal import _rider_ctx, rider_login_required
from .views_vendor_portal import _company_name

TABS = {'open': 'Open', 'closed': 'Closed'}


def _split(qs, tab):
    return qs.filter(status__in=('open', 'under_review')) if tab == 'open' \
        else qs.filter(status__in=('resolved', 'rejected'))


def _rows(qs, party):
    out = []
    for d in qs[:100]:
        out.append({'d': d, 'customer': logic.short_name(d.customer),
                    'responded': bool(getattr(d, f'{party}_responded_at'))})
    return out


def _detail_ctx(d, party):
    items = d.sale_order.items.select_related('product')
    return {'d': d, 'order': d.sale_order, 'items': items, 'customer': logic.short_name(d.customer),
            'party': party, 'responded': bool(getattr(d, f'{party}_responded_at')),
            'my_response': getattr(d, f'{party}_response'), 'my_photo': getattr(d, f'{party}_photo'),
            'store': store_orders.store_name(d.sale_order.vendor_id) if d.sale_order.vendor_id else ''}


# ------------------------------------------------------------------ vendor
@vendor_login_required
def vendor_disputes(request):
    vendor = request.user.vendor_profile.vendor
    tab = request.GET.get('tab', 'open')
    if tab not in TABS:
        tab = 'open'
    base = logic.disputes_for('vendor', vendor)
    return render(request, 'customer_portal/vendor/disputes.html', {
        'rows': _rows(_split(base, tab), 'vendor'), 'tab': tab, 'tabs': TABS,
        'pending': logic.needs_response_count('vendor', vendor),
        'company_name': _company_name(),
    })


@vendor_login_required
@require_http_methods(['GET', 'POST'])
def vendor_dispute_detail(request, pk):
    vendor = request.user.vendor_profile.vendor
    d = get_object_or_404(logic.disputes_for('vendor', vendor), pk=pk)
    if request.method == 'POST':
        try:
            logic.submit_response(d, 'vendor', request.POST.get('response', ''), request.FILES.get('photo'))
            messages.success(request, '✅ Aap ka jawab bhej diya gaya.')
        except logic.DisputeError as exc:
            messages.error(request, f'❌ {exc}')
        return redirect('vendor_dispute_detail', pk=d.pk)
    return render(request, 'customer_portal/vendor/dispute_detail.html',
                  dict(_detail_ctx(d, 'vendor'), company_name=_company_name()))


# ------------------------------------------------------------------ rider
@rider_login_required
def rider_disputes(request):
    rider = request.user.rider_profile
    tab = request.GET.get('tab', 'open')
    if tab not in TABS:
        tab = 'open'
    base = logic.disputes_for('rider', rider)
    return render(request, 'customer_portal/rider/disputes.html', _rider_ctx(
        request, 'disputes', rows=_rows(_split(base, tab), 'rider'), tab=tab, tabs=TABS))


@rider_login_required
@require_http_methods(['GET', 'POST'])
def rider_dispute_detail(request, pk):
    rider = request.user.rider_profile
    d = get_object_or_404(logic.disputes_for('rider', rider), pk=pk)
    if request.method == 'POST':
        try:
            logic.submit_response(d, 'rider', request.POST.get('response', ''), request.FILES.get('photo'))
            messages.success(request, '✅ Aap ka jawab bhej diya gaya.')
        except logic.DisputeError as exc:
            messages.error(request, f'❌ {exc}')
        return redirect('rider_dispute_detail', pk=d.pk)
    return render(request, 'customer_portal/rider/dispute_detail.html',
                  _rider_ctx(request, 'disputes', **_detail_ctx(d, 'rider')))
