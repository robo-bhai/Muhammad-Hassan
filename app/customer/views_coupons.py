"""Customer side: coupon lagana / hatana (cart aur checkout page se)."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..shop_flags import flag_required
from . import coupons as coupon_logic
from . import store_orders


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')


def _back(request):
    nxt = request.POST.get('next', '')
    return redirect('checkout' if nxt == 'checkout' else 'cart_view')


@require_POST
@flag_required('shop_coupons_enabled', redirect_to='cart_view')
def apply_coupon(request):
    from decimal import Decimal
    cart = request.session.get('cart', {})
    code = (request.POST.get('code') or '').strip().upper().replace(' ', '')[:30]
    customer = None
    if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
        customer = request.user.customer_profile.customer

    if not cart:
        msg, ok, discount = 'Cart khali hai.', False, Decimal('0')
    elif not code:
        msg, ok, discount = 'Coupon code likhein.', False, Decimal('0')
    else:
        from .views_customer_portal import calculate_cart_data
        subtotal = calculate_cart_data(cart, customer=customer)['subtotal']
        vendor_id = store_orders.cart_store_id(cart) or 0
        coupon, discount, err = coupon_logic.validate(code, customer, vendor_id, subtotal)
        if err:
            msg, ok = err, False
        else:
            request.session[coupon_logic.SESSION_KEY] = coupon.code
            request.session.modified = True
            msg, ok = f'{coupon.code} laag gaya. Aap ne {discount:,.2f} bachaye.', True

    if _is_ajax(request):
        return JsonResponse({'success': ok, 'message': msg, 'discount': float(discount)}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, ('🏷️ ' if ok else '❌ ') + msg)
    return _back(request)


@require_POST
def remove_coupon(request):
    request.session.pop(coupon_logic.SESSION_KEY, None)
    request.session.modified = True
    if _is_ajax(request):
        return JsonResponse({'success': True})
    messages.info(request, 'Coupon removed.')
    return _back(request)
