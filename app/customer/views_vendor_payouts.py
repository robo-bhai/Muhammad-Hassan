"""Vendor portal: Payout request (vendor khud apni raqam maange).

- vendor_payouts       : /shop/vendor/payouts/  (summary, account save, naya request, history)
- vendor_payout_cancel : pending request wapas lena

Hisaab aur qawaid `payout_requests.py` me hain; yahan sirf form/POST ka kaam hai.
"""
import logging

from django.contrib import messages
from .vendor_access import get_vendor_profile
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import VendorProfile
from ..shop_flags import flag_required
from . import payout_requests
from .payout_requests import PayoutError

logger = logging.getLogger(__name__)

FLAG = 'vendor_payout_request_enabled'


def _company_name():
    from ..models import CompanyInfo
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


@vendor_login_required
@flag_required(FLAG, redirect_to='vendor_dashboard')
def vendor_payouts(request):
    profile = get_vendor_profile(request.user)
    vendor = profile.vendor

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'save_account':
                # Account badalna paise ka rasta badalta hai, is liye password dobara maangte hain
                if not request.user.check_password(request.POST.get('password', '')):
                    raise PayoutError('Password galat hai. Account badalne ke liye apna password likhen.')
                payout_requests.save_account(
                    profile, request.POST.get('method', ''), request.POST.get('account_title', ''),
                    request.POST.get('account_no', ''))
                messages.success(request, '✅ Payout account save ho gaya.')
            elif action == 'request':
                req = payout_requests.create_request(profile, request.POST.get('amount', ''),
                                                     request.POST.get('note', ''))
                messages.success(request, f'✅ Request bhej di gayi: Rs. {req.amount:,.2f}. '
                                          f'Admin jald hi payment karega.')
            else:
                raise PayoutError('Galat action.')
        except PayoutError as exc:
            messages.error(request, f'❌ {exc}')
        except Exception:
            logger.exception('vendor payout POST failed (vendor=%s)', vendor.pk)
            messages.error(request, '❌ Kuch masla aa gaya. Dobara koshish karen.')
        return redirect('vendor_payouts')

    profile = VendorProfile.objects.get(pk=profile.pk)
    return render(request, 'customer_portal/vendor/payouts.html', {
        'page_title': 'Payout Requests',
        'profile': profile,
        'w': payout_requests.withdrawable(vendor),
        'requests': vendor.payout_requests.all()[:30],
        'methods': VendorProfile.PAYOUT_METHODS,
        'company_name': _company_name(),
    })


@require_POST
@vendor_login_required
@flag_required(FLAG, redirect_to='vendor_dashboard')
def vendor_payout_cancel(request, pk):
    try:
        payout_requests.cancel_request(get_vendor_profile(request.user), pk)
        messages.success(request, '✅ Request cancel kar di gayi.')
    except PayoutError as exc:
        messages.error(request, f'❌ {exc}')
    return redirect('vendor_payouts')
