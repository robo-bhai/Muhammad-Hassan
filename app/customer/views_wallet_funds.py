"""Customer portal: wallet top-up request, gift card khareedna aur redeem karna."""
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..shop_flags import flag_required
from . import wallet_funds
from .views_favorites import current_customer


def _request(request, kind):
    customer = current_customer(request)
    if not customer:
        messages.error(request, 'Only a customer account can do this.')
        return redirect('wallet_page')
    post = request.POST
    req, err = wallet_funds.create_request(
        customer, kind, wallet_funds.parse_amount(post.get('amount')), post.get('method', ''),
        post.get('reference', ''), post.get('recipient_name', ''), post.get('message', ''))
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Request sent. We will confirm after checking your payment.')
    return redirect('wallet_page')


@require_POST
@customer_login_required
@flag_required('shop_wallet_enabled')
@flag_required('shop_gift_cards_enabled')
def topup_request(request):
    return _request(request, 'topup')


@require_POST
@customer_login_required
@flag_required('shop_wallet_enabled')
@flag_required('shop_gift_cards_enabled')
def gift_buy(request):
    return _request(request, 'gift')


@require_POST
@customer_login_required
@flag_required('shop_wallet_enabled')
@flag_required('shop_gift_cards_enabled')
def gift_redeem(request):
    customer = current_customer(request)
    if not customer:
        messages.error(request, 'Only a customer account can redeem a gift card.')
        return redirect('wallet_page')
    ok, msg = wallet_funds.redeem(customer, request.POST.get('code', ''))
    (messages.success if ok else messages.error)(request, msg)
    return redirect('wallet_page')
