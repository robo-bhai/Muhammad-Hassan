"""Password reset (customer + vendor): phone likho -> email par 6-digit code -> naya password.

- Code CustomerOTP (purpose='forgot_password') se jata hai: 5 minute, 5 ghalat koshishon par 30 min lock.
- Jawab hamesha ek jaisa hota hai (phone registered ho ya na ho) taake koi phone number check na kar sake.
- Naya password portal policy (app/utils/password_policy.py) se guzarta hai.
- Rider ke paas email nahi hota: unka password admin/manager 'Riders' page se badalta hai.
"""
import logging

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..models import CompanyInfo, Customer, CustomerOTP, VendorProfile
from ..utils.password_policy import password_errors
from .views_customer_auth import get_client_ip, is_valid_phone, normalize_phone

logger = logging.getLogger(__name__)

SESSION_KEY = 'fp_phone'
REQ_PER_IP = 10          # ek IP se ghante mein code mangwane ki had
VERIFY_PER_IP = 20       # ek IP se ghante mein code/password ki koshishen
HOUR = 3600
GENERIC_MSG = ('Agar yeh phone registered hai aur account par email maujood hai to 6-digit code bhej diya gaya hai '
               '(5 minute valid). Spam folder bhi dekh lein.')


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'Shop'


def _find_account(phone):
    """(kind, user, name, email, login_url_name) ya None. Staff/admin accounts is raste se reset nahi hote."""
    customer = Customer.objects.filter(contact_number=phone).first()
    if customer and hasattr(customer, 'portal_profile'):
        user = customer.portal_profile.user
        if user and not (user.is_staff or user.is_superuser):
            return ('customer', user, customer.name, (customer.email or user.email or '').strip(), 'customer_login')
    vp = (VendorProfile.objects.select_related('user', 'vendor')
          .filter(vendor__contact_number=phone).first())
    if vp and vp.user and not (vp.user.is_staff or vp.user.is_superuser):
        email = (vp.user.email or getattr(vp.vendor, 'email', '') or '').strip()
        return ('vendor', vp.user, vp.business_name, email, 'vendor_login')
    return None


def _bump(key, seconds=HOUR):
    n = cache.get(key, 0) + 1
    cache.set(key, n, seconds)
    return n


@require_http_methods(['GET', 'POST'])
def forgot_password(request):
    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '').strip()[:20]
        if not phone_raw or not is_valid_phone(phone_raw):
            messages.error(request, '❌ Sahi phone number likhein.')
            return redirect('forgot_password')
        phone = normalize_phone(phone_raw)
        ip = get_client_ip(request) or ''

        if cache.get(f'fp_req_ip:{ip}', 0) >= REQ_PER_IP:
            messages.error(request, '🔒 Bohat zyada koshishen. Thori der baad dobara try karein.')
            return redirect('forgot_password')
        _bump(f'fp_req_ip:{ip}')

        account = _find_account(phone)
        if account and account[3]:
            kind, user, name, email, _login = account
            try:
                CustomerOTP.generate_otp(
                    phone=phone, purpose='forgot_password', customer_name=name, customer_email=email,
                    ip_address=ip, user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                )
            except Exception as exc:       # 15 minute mein 3 se zyada requests, ya email ka masla
                logger.warning('forgot_password OTP not sent for %s: %s', phone, exc)
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
        messages.info(request, 'Pehle apna phone number likhein.')
        return redirect('forgot_password')

    if request.method == 'POST':
        code = (request.POST.get('code') or '').strip()[:6]
        password = request.POST.get('password', '')
        confirm = request.POST.get('confirm_password', '')
        ip = get_client_ip(request) or ''

        if cache.get(f'fp_ver_ip:{ip}', 0) >= VERIFY_PER_IP:
            messages.error(request, '🔒 Bohat zyada koshishen. Thori der baad dobara try karein.')
            return redirect('reset_password')
        _bump(f'fp_ver_ip:{ip}')

        account = _find_account(phone)
        hints = (account[2], phone, account[1].username, account[3]) if account else (phone,)
        pw_errors = password_errors(password, hints)

        if not (code.isdigit() and len(code) == 6):
            messages.error(request, '❌ 6-digit code likhein.')
        elif password != confirm:
            messages.error(request, '❌ Dono password aik jaise likhein.')
        elif pw_errors:
            messages.error(request, '❌ ' + pw_errors[0])
        else:
            ok, _otp, msg = CustomerOTP.find_and_verify(phone, code, purpose='forgot_password')
            if not ok or not account:
                messages.error(request, '❌ ' + (msg if not ok else 'Code ghalat ya expire ho chuka hai.'))
            else:
                user = account[1]
                user.set_password(password)        # purane sessions khud invalid ho jate hain
                user.save(update_fields=['password'])
                CustomerOTP.objects.filter(phone=phone, purpose='forgot_password', is_used=False).delete()
                cache.delete(f'fp_ver_ip:{ip}')
                request.session.pop(SESSION_KEY, None)
                messages.success(request, '✅ Password badal gaya. Ab naye password se login karein.')
                return redirect(account[4])
        return redirect('reset_password')

    masked = phone[:5] + '*****' + phone[-2:]
    return render(request, 'customer_portal/auth/reset_password.html', {
        'page_title': 'Reset password', 'company_name': _company_name(), 'masked_phone': masked,
    })
