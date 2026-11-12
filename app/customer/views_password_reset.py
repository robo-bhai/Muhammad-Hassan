"""Password reset (customer + vendor): phone likho -> email par 6-digit code -> naya password.

- Code CustomerOTP (purpose='forgot_password') se jata hai: 5 minute, 5 ghalat koshishon par 30 min lock.
- Jawab hamesha ek jaisa hota hai (phone registered ho ya na ho) taake koi phone number check na kar sake.
- Naya password portal policy (app/utils/password_policy.py) se guzarta hai.
- Rider ke paas email nahi hota: unka password admin/manager 'Riders' page se badalta hai.
"""
import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..models import CompanyInfo
from ..utils import password_reset as pr
from .views_customer_auth import get_client_ip, is_valid_phone, normalize_phone

logger = logging.getLogger(__name__)

SESSION_KEY = 'fp_phone'
GENERIC_MSG = ('If this phone is registered, a 6-digit code has been sent (by WhatsApp or email, valid for 5 minutes). '
               'Please also check your spam folder.')
TOO_MANY_MSG = '🔒 Too many attempts. Please try again later.'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'Shop'


@require_http_methods(['GET', 'POST'])
def forgot_password(request):
    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        if not phone_raw or not is_valid_phone(phone_raw):
            messages.error(request, '❌ Enter a valid phone number.')
            return redirect('forgot_password')
        phone = normalize_phone(phone_raw)
        ip = get_client_ip(request) or ''

        if pr.too_many('fp_req_ip', ip, pr.REQ_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('forgot_password')
        pr.bump(f'fp_req_ip:{ip}')

        account = pr.find_account(phone, pr.SHOP_KINDS)
        if account and pr.can_deliver(account):
            pr.request_code(account, ip, request.META.get('HTTP_USER_AGENT', ''))
        request.session[SESSION_KEY] = phone
        request.session.modified = True
        messages.info(request, GENERIC_MSG)
        return redirect('reset_password')

    return render(request, 'customer_portal/auth/forgot_password.html', {
        'page_title': 'Forgot password', 'company_name': _company_name(),
    })


@require_http_methods(['GET', 'POST'])
def reset_password(request):
    phone = request.session.get(SESSION_KEY)
    if not phone:
        messages.info(request, 'Please enter your phone number first.')
        return redirect('forgot_password')

    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()[:6]
        ip = get_client_ip(request) or ''

        if pr.too_many('fp_ver_ip', ip, pr.VERIFY_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('reset_password')
        pr.bump(f'fp_ver_ip:{ip}')

        account = pr.find_account(phone, pr.SHOP_KINDS)
        if not account:
            messages.error(request, '❌ The code is wrong or has expired.')
            return redirect('reset_password')

        ok, msg = pr.complete_reset(account, code, request.POST.get('password', ''),
                                    request.POST.get('confirm_password', ''), ip)
        if ok:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, '✅ ' + msg)
            return redirect(account.login_url_name)
        messages.error(request, '❌ ' + msg)
        return redirect('reset_password')

    masked = phone[:5] + '*****' + phone[-2:]
    return render(request, 'customer_portal/auth/reset_password.html', {
        'page_title': 'Reset password', 'company_name': _company_name(), 'masked_phone': masked,
    })
