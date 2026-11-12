"""Rider ka forgot password: phone -> code -> naya password.

Code do raston se milta hai:
  1. WhatsApp par automatic (agar WHATSAPP_* settings hon) ya email (agar rider ke account par ho).
  2. Warna admin ko notification jati hai (OTP management / Riders page par code nazar aata hai)
     aur admin rider ko phone par code bata deta hai.
Jawab hamesha ek jaisa hota hai (phone registered ho ya na ho). Engine: app/utils/password_reset.py
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..models import CompanyInfo
from ..shop_flags import flag_required
from ..utils import password_reset as pr
from ..utils import whatsapp_otp
from .views_customer_auth import get_client_ip, is_valid_phone, normalize_phone

SESSION_KEY = 'rfp_phone'
TOO_MANY_MSG = '🔒 Too many attempts. Please try again later.'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'Shop'


@flag_required('rider_login_enabled', redirect_to='shop_home')
@require_http_methods(['GET', 'POST'])
def rider_forgot_password(request):
    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        if not phone_raw or not is_valid_phone(phone_raw):
            messages.error(request, '❌ Enter a valid phone number.')
            return redirect('rider_forgot_password')
        phone = normalize_phone(phone_raw)
        ip = get_client_ip(request) or ''

        if pr.too_many('rfp_req_ip', ip, pr.REQ_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('rider_forgot_password')
        pr.bump(f'rfp_req_ip:{ip}')

        account = pr.find_account(phone, pr.RIDER_KINDS)
        if account:
            pr.request_code(account, ip, request.META.get('HTTP_USER_AGENT', ''))
        request.session[SESSION_KEY] = phone
        request.session.modified = True
        if whatsapp_otp.is_configured():
            messages.info(request, 'If this phone belongs to a registered rider, a 6-digit code has been sent on WhatsApp (valid for 5 minutes).')
        else:
            messages.info(request, 'If this phone belongs to a registered rider, the manager has been informed. '
                                   'Enter the 6-digit code from the manager here (valid for 5 minutes).')
        return redirect('rider_reset_password')

    return render(request, 'customer_portal/rider/forgot_password.html', {
        'company_name': _company_name(), 'whatsapp': whatsapp_otp.is_configured(),
    })


@flag_required('rider_login_enabled', redirect_to='shop_home')
@require_http_methods(['GET', 'POST'])
def rider_reset_password(request):
    phone = request.session.get(SESSION_KEY)
    if not phone:
        messages.info(request, 'Please enter your phone number first.')
        return redirect('rider_forgot_password')

    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()[:6]
        ip = get_client_ip(request) or ''

        if pr.too_many('rfp_ver_ip', ip, pr.VERIFY_PER_IP):
            messages.error(request, TOO_MANY_MSG)
            return redirect('rider_reset_password')
        pr.bump(f'rfp_ver_ip:{ip}')

        account = pr.find_account(phone, pr.RIDER_KINDS)
        if not account:
            messages.error(request, '❌ The code is wrong or has expired.')
            return redirect('rider_reset_password')

        ok, msg = pr.complete_reset(account, code, request.POST.get('password', ''),
                                    request.POST.get('confirm_password', ''), ip)
        if ok:
            request.session.pop(SESSION_KEY, None)
            messages.success(request, '✅ ' + msg)
            return redirect(account.login_url_name)
        messages.error(request, '❌ ' + msg)
        return redirect('rider_reset_password')

    masked = phone[:5] + '*****' + phone[-2:]
    return render(request, 'customer_portal/rider/reset_password.html', {
        'company_name': _company_name(), 'masked_phone': masked, 'whatsapp': whatsapp_otp.is_configured(),
    })
