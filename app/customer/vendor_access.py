"""Vendor portal access: owner, staff aur branches.

Poora portal `get_vendor_profile(user)` se chalta hai:
- Owner: apna main store, ya (agar usne Branches page se switch kiya ho) wo branch.
- Staff: sirf apni store.
Branch = alag VendorProfile (parent = owner ka main profile) - alag products, orders, payouts.
"""

ROLE_OWNER = 'owner'

# Sirf owner: paise, store ki settings, staff, branches
OWNER_ONLY = {
    'vendor_payouts', 'vendor_payout_cancel', 'vendor_store_settings',
    'vendor_staff', 'vendor_staff_action', 'vendor_set_location',
    'vendor_branches', 'vendor_branch_action', 'vendor_branch_copy',
}

# 'orders' role sirf ye pages dekh sakta hai
ORDERS_ROLE_ALLOWED = {
    'vendor_dashboard', 'vendor_orders', 'vendor_order_action', 'vendor_assign_rider', 'vendor_switch_store',
    'vendor_orders_poll', 'vendor_pause', 'vendor_logout', 'vendor_disputes', 'vendor_dispute_detail',
}

SESSION_KEY = 'vendor_branch_id'


def _staff_record(user):
    rec = getattr(user, 'vendor_staff', None)
    if rec is not None and rec.is_active and rec.store_id:
        return rec
    return None


def get_vendor_profile(user):
    """Owner ka (active) VendorProfile, ya active staff ki store ka VendorProfile. Warna None."""
    if not getattr(user, 'is_authenticated', False):
        return None
    owner = getattr(user, 'vendor_profile', None)
    if owner is not None:
        active = getattr(user, '_active_branch', None)
        return active if active is not None else owner
    rec = _staff_record(user)
    if rec is None:
        return None
    active = getattr(user, '_active_branch', None)
    return active if active is not None else rec.store


def vendor_role(user):
    """'owner', 'manager', 'orders' ya None."""
    if getattr(user, 'vendor_profile', None) is not None:
        return ROLE_OWNER
    rec = _staff_record(user)
    return rec.role if rec else None


def role_can_open(role, url_name):
    if role == ROLE_OWNER:
        return True
    if role == 'manager':
        return url_name not in OWNER_ONLY
    if role == 'orders':
        return url_name in ORDERS_ROLE_ALLOWED
    return False


def activate_branch(request):
    """Jo store (branch) chuni ho wo is request ke liye active kar do (decorator se chalta hai).
    Owner: apni branches mein se. Staff: apne chune hue stores mein se."""
    user = request.user
    user._active_branch = None
    bid = request.session.get(SESSION_KEY)
    if not bid:
        return
    owner = getattr(user, 'vendor_profile', None)
    if owner is not None:
        pool = owner.branches
        home_id = owner.pk
    else:
        rec = _staff_record(user)
        if rec is None:
            return
        pool = rec.extra_stores
        home_id = rec.store_id
    store = pool.filter(pk=bid).first()
    if store is None:
        if str(bid) != str(home_id):
            request.session.pop(SESSION_KEY, None)    # store hat gayi ya ab access nahi
        return
    user._active_branch = store


def accessible_profiles(user):
    """Is user ke saare stores: owner = main + branches, staff = apni store."""
    if not getattr(user, 'is_authenticated', False):
        return []
    owner = getattr(user, 'vendor_profile', None)
    if owner is not None:
        return [owner] + list(owner.branches.all())
    rec = _staff_record(user)
    if rec is None:
        return []
    return [rec.store] + list(rec.extra_stores.exclude(pk=rec.store_id))


def profile_for_vendor(user, vendor_id):
    """Is user ka wo store jis ka Vendor vendor_id hai (order kis branch ka hai). Warna None."""
    if not vendor_id:
        return None
    for p in accessible_profiles(user):
        if p.vendor_id == vendor_id:
            return p
    return None


def notify_users(profile):
    """Is store ke naye order par kin users ko notification jaye:
    owner (branch ho to us ka owner) + wo active staff jo is store par kaam karta hai
    (is ka apna store ho ya extra stores me shamil)."""
    from django.db.models import Q
    from ..models import VendorStaff
    root = profile.parent if profile.parent_id else profile
    users = [root.user]
    staff = (VendorStaff.objects.filter(is_active=True)
             .filter(Q(store=profile) | Q(extra_stores=profile))
             .select_related('user').distinct())
    for rec in staff:
        if rec.user and rec.user.is_active:
            users.append(rec.user)
    seen, out = set(), []
    for u in users:
        if u and u.pk not in seen:
            seen.add(u.pk)
            out.append(u)
    return out
