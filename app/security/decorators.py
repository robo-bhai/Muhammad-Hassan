"""
Custom Decorators for Customer Portal
======================================
- customer_login_required: for Customer portal pages
- staff_required: for staff/admin only
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.urls import reverse


def customer_suspension_notice(user):
    """Customer suspend ho to usko dikhane wala message, warna None.
    Staff/admin kabhi suspend nahi hote."""
    if not user or user.is_staff or user.is_superuser:
        return None
    profile = getattr(user, 'customer_profile', None)
    if profile is None or not profile.is_suspended:
        return None
    msg = '⛔ Aap ka account suspend kar diya gaya hai.'
    if profile.suspended_reason:
        msg += f' Wajah: {profile.suspended_reason}.'
    return msg + ' Madad ke liye store se rabta karein.'


def customer_login_required(view_func):
    """
    ✅ Custom decorator for customer portal pages
    
    Behavior:
    - If the user is not authenticated → redirect to customer_login (with next)
    - If a customer → run the view
    - If admin/staff → allowed (bypass)
    - If any other user → redirect to shop_home
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # ==========================================
        # CHECK 1: User authenticated hai?
        # ==========================================
        if not request.user.is_authenticated:
            messages.warning(request, '🛒 Please log in first')
            next_url = request.get_full_path()
            return redirect(f"{reverse('customer_login')}?next={next_url}")
        
        # ==========================================
        # CHECK 2: Customer hai ya admin/staff?
        # ==========================================
        is_customer = hasattr(request.user, 'customer_profile')
        is_admin = request.user.is_staff or request.user.is_superuser
        
        if is_customer:
            # ⛔ Suspend customer: purani login session bhi band
            notice = customer_suspension_notice(request.user)
            if notice:
                logout(request)
                messages.error(request, notice)
                return redirect('customer_login')
            # ✅ Customer hai — allowed
            return view_func(request, *args, **kwargs)
        
        if is_admin:
            # ✅ Admin/staff hai — allowed (bypass)
            return view_func(request, *args, **kwargs)
        
        # ❌ Any other user — access denied
        messages.error(request, '❌ This page is for customers only')
        return redirect('shop_home')
    
    return wrapper


def staff_required(view_func):
    """
    ✅ For staff/admin users only
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, '🔒 Please log in first')
            return redirect('login')
        
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, '❌ Access denied')
            return redirect('shop_home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper

def vendor_login_required(view_func):
    """
    Vendor portal pages ke liye.

    - Login nahi -> vendor_login (next ke sath)
    - Vendor account hai -> view chalao
    - Koi aur user -> shop_home
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, '🔒 Please log in as a vendor first')
            return redirect(f"{reverse('vendor_login')}?next={request.get_full_path()}")

        from ..customer.vendor_access import (
            activate_branch, get_vendor_profile, vendor_role, role_can_open)
        activate_branch(request)
        if get_vendor_profile(request.user) is not None:
            match = getattr(request, 'resolver_match', None)
            url_name = match.url_name if match else ''
            if role_can_open(vendor_role(request.user), url_name):
                return view_func(request, *args, **kwargs)
            messages.error(request, '🔒 Your staff role cannot open this page')
            return redirect('vendor_dashboard')

        messages.error(request, '❌ This page is for vendors only')
        return redirect('shop_home')

    return wrapper
