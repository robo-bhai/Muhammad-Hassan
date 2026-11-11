"""
Reorder: pichla order ek click se dobara cart mein.

- Sirf apna order (customer_profile.customer).
- Purana cart replace hota hai (cart mein ek waqt mein ek hi store).
- Jo item ab available nahi (inactive / stock khatam / store band / option nahi raha) usay chhor deta hai
  aur customer ko bata deta hai. Price hamesha naye sire se nikalti hai (purani price par bharosa nahi).
"""
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import Inventory, Product, SaleOrder
from ..models.trade.product_options import resolve_selection
from . import cart_options


def _option_ids_from_key(options_key):
    """SaleOrderItem.options_key '3-7' ya '3-7:ab12cd34' -> [3, 7]."""
    head = (options_key or '').split(':')[0]
    return cart_options.parse_option_ids(head.replace('-', ',')) if head else []


@customer_login_required
@require_POST
def reorder(request, order_id):
    from .views_customer_portal import get_product_final_price, store_closed_message

    if not hasattr(request.user, 'customer_profile'):
        return redirect('shop_home')
    customer = request.user.customer_profile.customer
    order = get_object_or_404(SaleOrder, pk=order_id, customer=customer)

    cart, skipped = {}, []
    for it in order.items.select_related('product', 'product__vendor'):
        p = it.product
        label = p.name
        if not p.is_active or store_closed_message(p):
            skipped.append(f'{label} (abhi available nahi)')
            continue

        stock = Inventory.objects.filter(product=p).aggregate(t=Sum('stock'))['t'] or 0
        if stock <= 0:
            skipped.append(f'{label} (stock khatam)')
            continue

        chosen, extras, err = resolve_selection(p, _option_ids_from_key(it.options_key))
        if err:
            skipped.append(f'{label} (option badal gaya)')
            continue

        qty = max(1, int(round(it.qty or 1)))
        key = cart_options.make_cart_key(p.id, [o.id for o in chosen], it.note)
        already = cart_options.units_in_cart(cart, p.id)
        allowed = int(stock) - already
        if allowed <= 0:
            skipped.append(f'{label} (stock khatam)')
            continue
        if qty > allowed:
            qty = allowed
            skipped.append(f'{label} (sirf {allowed} mojood)')

        price = Decimal(str(get_product_final_price(p))) + extras
        if key in cart:
            cart[key]['quantity'] += qty
        else:
            cart[key] = {
                'product_id': p.id,
                'name': p.name,
                'price': float(price),
                'quantity': qty,
                'image': p.image.url if p.image else None,
                'vendor_id': p.vendor_id or 0,
                'cart_key': key,
                'option_ids': [o.id for o in chosen],
                'options_text': cart_options.options_text(chosen),
                'options_extra': float(extras),
                'note': it.note or '',
            }

    if not cart:
        messages.error(request, 'None of the items in this order are available right now.')
        return redirect('order_detail_customer', order_id=order.id)

    for k in ('buy_now_mode', 'buy_now_product_id'):
        request.session.pop(k, None)
    request.session['cart'] = cart
    request.session.modified = True

    if skipped:
        messages.warning(request, 'Ye items cart mein nahi aaye: ' + ', '.join(skipped))
    else:
        messages.success(request, 'Your previous order is in the cart. Please review it and place the order.')
    return redirect('cart_view')
