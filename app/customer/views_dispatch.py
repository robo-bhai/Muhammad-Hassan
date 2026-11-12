"""Auto dispatch ke views: rider reject, vendor store location."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import SaleOrder, VendorProfile
from . import dispatch
from .views_live_tracking import parse_coords
from .views_rider_portal import ACTIVE_STATUSES, MAX_ACTIVE_ORDERS, rider_login_required


@rider_login_required
@require_POST
def rider_decline_order(request, pk):
    rider = request.user.rider_profile
    order = SaleOrder.objects.filter(pk=pk, status='ready').first()
    if order and dispatch.can_take(order, rider, MAX_ACTIVE_ORDERS, ACTIVE_STATUSES):
        dispatch.decline(order, rider)
        messages.info(request, 'Order rejected. You will not see it again.')
    return redirect('rider_home')


@vendor_login_required
@require_POST
def vendor_set_location(request):
    coords = parse_coords(request.POST.get('lat'), request.POST.get('lng'))
    if coords is None:
        return JsonResponse({'ok': False, 'error': 'bad_coords'}, status=400)
    VendorProfile.objects.filter(pk=request.user.vendor_profile.pk).update(lat=coords[0], lng=coords[1])
    return JsonResponse({'ok': True})
