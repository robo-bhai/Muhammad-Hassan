"""Customer: delivered order par "Report a problem" (dispute)."""
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import SaleOrder
from ..shop_flags import flag_required
from . import disputes

logger = logging.getLogger(__name__)


@flag_required('customer_can_dispute_orders')
@customer_login_required
@require_POST
def dispute_create(request, order_id):
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Access denied')
        return redirect('shop_home')
    customer = request.user.customer_profile.customer
    order = get_object_or_404(SaleOrder, id=order_id, customer=customer)
    try:
        disputes.open_dispute(order, request.POST.get('reason', ''), request.POST.get('description', ''),
                              request.FILES.get('photo'))
    except disputes.DisputeError as exc:
        messages.error(request, f'❌ {exc}')
    else:
        messages.success(request, '✅ Your issue has been recorded. We will reply soon.')
    return redirect('order_detail_customer', order_id=order.id)
