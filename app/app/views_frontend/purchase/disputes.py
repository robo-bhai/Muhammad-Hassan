"""Frontend views: purchase/disputes

Admin ki dispute queue: list (status filter + search) aur detail (review, wallet refund ya reject).
Permissions: dekhna = view_vendors, faisla karna = edit_vendors (vendor approvals wali).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ...customer import disputes as logic
from ...models import DeliveryInfo, OrderDispute, OrderTracking
from ...security.permissions import perm_required

STATUS_TABS = ('open', 'under_review', 'resolved', 'rejected', 'all')


@login_required
@perm_required('view_vendors')
def dispute_list(request):
    status = request.GET.get('status', 'open')
    if status not in STATUS_TABS:
        status = 'open'
    search = request.GET.get('search', '').strip()

    base = OrderDispute.objects.select_related('sale_order', 'customer', 'vendor', 'rider')
    counts = {s: base.filter(status=s).count() for s in ('open', 'under_review', 'resolved', 'rejected')}
    counts['all'] = sum(counts.values())

    qs = base if status == 'all' else base.filter(status=status)
    if search:
        qs = qs.filter(Q(sale_order__order_no__icontains=search) | Q(customer__name__icontains=search)
                       | Q(vendor__name__icontains=search))
    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'disputes/list.html', {
        'page': page, 'status': status, 'search': search, 'counts': counts, 'tabs': STATUS_TABS,
    })


@login_required
@perm_required('view_vendors', post='edit_vendors')
def dispute_detail(request, pk):
    dispute = get_object_or_404(
        OrderDispute.objects.select_related('sale_order', 'customer', 'vendor', 'rider'), pk=pk)
    order = dispute.sale_order

    if request.method == 'POST':
        action = request.POST.get('action', '')
        try:
            if action == 'review':
                logic.mark_under_review(dispute, request.user)
                messages.success(request, 'Dispute review mein daal diya gaya.')
            else:
                logic.resolve_dispute(dispute, action, request.user,
                                      amount=request.POST.get('amount'), note=request.POST.get('note', ''))
                messages.success(request, 'Faisla darj ho gaya, customer ko khabar kar di gayi.')
        except logic.DisputeError as exc:
            messages.error(request, str(exc))
        return redirect('dispute_detail', pk=dispute.pk)

    return render(request, 'disputes/detail.html', {
        'dispute': dispute,
        'order': order,
        'items': order.items.select_related('product'),
        'max_refund': logic.max_refund(order),
        'delivery': DeliveryInfo.objects.filter(sale_order=order).select_related('rider').first(),
        'timeline': OrderTracking.objects.filter(sale_order=order).order_by('timestamp'),
    })
