"""
Vendor payout request - hisaab aur qawaid ek jagah (views aur admin dono yahin se kaam karte hain).

Flow:
  1. Vendor apna payout account save karta hai (password dobara dekar).
  2. Vendor `create_request` se raqam maangta hai. Raqam `withdrawable()` se zyada nahi ho sakti.
  3. Admin `mark_paid` karta hai -> ek VendorPayout banta hai (purana hisaab `vendor_earnings` wahi rehta hai)
     ya `reject` karta hai.

`withdrawable()` = baqi balance (vendor_earnings) minus teen cheezein jo abhi nikalne ke qabil nahi:
  - dispute window: pichhle PAYOUT_HOLD_DAYS din ki bikri ka vendor hissa,
  - rider ke paas phansa hua COD cash: jo cash rider ne abhi shop ko jama nahi karaya (FIFO: sab se nayi
    deliveries pehle "phansi hui" maani jati hain), un orders ka vendor hissa,
  - pehle se pending request ki raqam.

Settings > Shop se badalne wali values: payout_min_amount (default 500), payout_hold_days (default 2).
"""
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

CENT = Decimal('0.01')
ZERO = Decimal('0.00')
MAX_REQUEST_AMOUNT = Decimal('99999999.99')

MOBILE_METHODS = ('jazzcash', 'easypaisa')
_LINE = ExpressionWrapper(F('qty') * F('cost_price'), output_field=DecimalField(max_digits=18, decimal_places=2))
_EXTRA = ExpressionWrapper(F('qty') * F('options_extra_share'),
                           output_field=DecimalField(max_digits=18, decimal_places=2))


class PayoutError(Exception):
    """Aisi ghalti jo seedha vendor/admin ko dikhai ja sakti hai."""


# ---------------------------------------------------------------- settings
def payout_settings():
    from .offers import setting_decimal
    return {
        'min_amount': max(setting_decimal('payout_min_amount', '500'), Decimal('1')),
        'hold_days': max(int(setting_decimal('payout_hold_days', '2')), 0),
    }


# ---------------------------------------------------------------- hisaab
def _money(value):
    return Decimal(value or 0).quantize(CENT, ROUND_HALF_UP)


def _vendor_share(vendor, since=None, sale=None):
    """Vendor ka hissa (vendor_earnings wali hi formula): batch cost + options extras.
    since: sirf is waqt ke baad ki bikri; sale: sirf is ek invoice ki."""
    from app.models import SaleItem, SaleItemBatchUsage
    items = SaleItem.objects.filter(product__vendor=vendor)
    usage = SaleItemBatchUsage.objects.filter(sale_item__product__vendor=vendor)
    if since is not None:
        items = items.filter(sale__sale_date__gt=since)
        usage = usage.filter(sale_item__sale__sale_date__gt=since)
    if sale is not None:
        items = items.filter(sale=sale)
        usage = usage.filter(sale_item__sale=sale)
    a = usage.aggregate(t=Sum(_LINE))['t']
    b = items.aggregate(t=Sum(_EXTRA))['t']
    return _money(Decimal(a or 0) + Decimal(b or 0))


def _cash_hold(vendor, cutoff):
    """Un orders ka vendor hissa jin ka COD cash abhi rider ke paas hai (shop ko jama nahi hua).
    cutoff: us waqt se nayi bikri pehle hi 'dispute window' me ginti ho chuki, dobara nahi ginte."""
    from app.models import DeliveryInfo, RiderSettlement
    rider_ids = (DeliveryInfo.objects
                 .filter(sale_order__vendor=vendor, rider__isnull=False, cash_collected__gt=0)
                 .values_list('rider_id', flat=True).distinct())
    held = ZERO
    for rid in rider_ids:
        collected = DeliveryInfo.objects.filter(rider_id=rid).aggregate(t=Sum('cash_collected'))['t'] or 0
        cash_in = RiderSettlement.objects.filter(rider_id=rid, kind='cash_in').aggregate(t=Sum('amount'))['t'] or 0
        remaining = Decimal(collected) - Decimal(cash_in)
        if remaining <= 0:
            continue
        # Sab se nayi deliveries ka cash pehle "phansa hua" hai (purani pehle settle hoti hain)
        deliveries = (DeliveryInfo.objects.filter(rider_id=rid, cash_collected__gt=0)
                      .select_related('sale_order__converted_to_sale').order_by('-id'))
        for di in deliveries:
            if remaining <= 0:
                break
            remaining -= Decimal(di.cash_collected)
            order = di.sale_order
            if order is None or order.vendor_id != vendor.id or order.converted_to_sale_id is None:
                continue
            sale = order.converted_to_sale
            if cutoff is not None and sale.sale_date > cutoff:
                continue
            held += _vendor_share(vendor, sale=sale)
    return _money(held)


def pending_amount(vendor):
    from app.models import VendorPayoutRequest
    return _money(VendorPayoutRequest.objects.filter(vendor=vendor, status='pending')
                  .aggregate(t=Sum('amount'))['t'])


def withdrawable(vendor):
    """{'balance','held_recent','held_cash','pending','available'} - available kabhi minus nahi."""
    from .vendor_commission import vendor_earnings
    cfg = payout_settings()
    balance = vendor_earnings(vendor)['balance']
    cutoff = timezone.now() - timedelta(days=cfg['hold_days']) if cfg['hold_days'] > 0 else None
    held_recent = _vendor_share(vendor, since=cutoff) if cutoff is not None else ZERO
    held_cash = _cash_hold(vendor, cutoff)
    pending = pending_amount(vendor)
    available = max(balance - held_recent - held_cash - pending, ZERO)
    return {
        'balance': balance, 'held_recent': held_recent, 'held_cash': held_cash,
        'pending': pending, 'available': available.quantize(CENT, ROUND_HALF_UP),
        'min_amount': cfg['min_amount'], 'hold_days': cfg['hold_days'],
    }


# ---------------------------------------------------------------- account
def clean_account_no(method, raw):
    """Spaces/dash hata kar account number; galat ho to PayoutError."""
    value = re.sub(r'[\s\-]', '', (raw or '')).upper()
    if method in MOBILE_METHODS:
        if not re.fullmatch(r'\+?\d{10,13}', value):
            raise PayoutError('Mobile account number sahi likhen (jaise 03001234567).')
    elif not re.fullmatch(r'[A-Z0-9]{8,34}', value):
        raise PayoutError('Bank account number / IBAN sahi likhen (8 se 34 harf ya number).')
    return value


def save_account(profile, method, title, account_no):
    from app.models import VendorProfile
    if method not in dict(VendorProfile.PAYOUT_METHODS):
        raise PayoutError('Payment ka tareeqa chunen.')
    title = ' '.join((title or '').split())[:100]
    if len(title) < 3:
        raise PayoutError('Account holder ka poora naam likhen.')
    profile.payout_method = method
    profile.payout_account_title = title
    profile.payout_account_no = clean_account_no(method, account_no)
    profile.save(update_fields=['payout_method', 'payout_account_title', 'payout_account_no'])
    return profile


# ---------------------------------------------------------------- vendor side
def parse_amount(raw):
    try:
        amount = Decimal(str(raw).replace(',', '').strip())
        if not amount.is_finite():          # 'NaN' / 'Infinity' / '-Infinity'
            raise InvalidOperation
        amount = amount.quantize(CENT, ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise PayoutError('Raqam sahi likhen.')
    if amount <= 0 or amount > MAX_REQUEST_AMOUNT:
        raise PayoutError('Raqam zero se zyada honi chahiye.')
    return amount


def create_request(profile, amount, note=''):
    """Naya payout request. Vendor ki profile row lock hoti hai, is liye ek saath do requests
    ek hi balance par nahi ban sakti (upar se database ka unique constraint bhi hai)."""
    from app.models import VendorProfile, VendorPayoutRequest
    with transaction.atomic():
        profile = VendorProfile.objects.select_for_update().select_related('vendor').get(pk=profile.pk)
        vendor = profile.vendor
        if not profile.is_approved:
            raise PayoutError('Aap ka account abhi approve nahi hua.')
        if not (profile.payout_method and profile.payout_account_title and profile.payout_account_no):
            raise PayoutError('Pehle apna payout account (naam aur number) save karen.')
        if VendorPayoutRequest.objects.filter(vendor=vendor, status='pending').exists():
            raise PayoutError('Aap ki ek request pehle se pending hai. Us ke nipatne ka intezar karen.')
        amount = parse_amount(amount)
        w = withdrawable(vendor)
        if amount < w['min_amount']:
            raise PayoutError(f"Kam az kam Rs. {w['min_amount']:,.0f} ki request ho sakti hai.")
        if amount > w['available']:
            raise PayoutError(f"Aap abhi zyada se zyada Rs. {w['available']:,.2f} nikal sakte hain.")
        try:
            with transaction.atomic():
                return VendorPayoutRequest.objects.create(
                    vendor=vendor, amount=amount, method=profile.payout_method,
                    account_title=profile.payout_account_title, account_no=profile.payout_account_no,
                    note=(note or '').strip()[:200])
        except IntegrityError:
            raise PayoutError('Aap ki ek request pehle se pending hai.')


def cancel_request(profile, pk):
    from app.models import VendorPayoutRequest
    with transaction.atomic():
        req = (VendorPayoutRequest.objects.select_for_update()
               .filter(pk=pk, vendor_id=profile.vendor_id).first())
        if req is None:
            raise PayoutError('Request nahi mili.')
        if req.status != 'pending':
            raise PayoutError('Ye request ab cancel nahi ho sakti.')
        req.status = 'cancelled'
        req.reviewed_at = timezone.now()
        req.save(update_fields=['status', 'reviewed_at'])
        return req


# ---------------------------------------------------------------- admin side
def mark_paid(request_id, admin_user, reference_no):
    """Admin ne paise bhej diye: VendorPayout banao aur request ko 'paid' karo (ek hi transaction me)."""
    from app.models import VendorPayout, VendorPayoutRequest, VendorProfile
    from .vendor_commission import vendor_earnings
    reference_no = (reference_no or '').strip()[:100]
    if not reference_no:
        raise PayoutError('Transaction ID / reference number likhna zaroori hai.')
    with transaction.atomic():
        req = VendorPayoutRequest.objects.select_for_update().select_related('vendor').get(pk=request_id)
        if req.status != 'pending':
            raise PayoutError('Ye request pehle hi nipat chuki hai.')
        # Vendor ki profile lock: usi waqt vendor ke hisaab me aur kuch na badle
        VendorProfile.objects.select_for_update().filter(vendor=req.vendor).first()
        balance = vendor_earnings(req.vendor)['balance']
        if req.amount > balance:
            raise PayoutError(f'Vendor ka baqi (Rs. {balance:,.2f}) request se kam hai. '
                              f'Pehle hisaab dekhen (shayad koi return/adjustment hua).')
        payout = VendorPayout.objects.create(
            vendor=req.vendor, amount=req.amount, method=req.method, reference_no=reference_no,
            notes=f'Payout request #{req.pk}', created_by=admin_user)
        req.status = 'paid'
        req.payout = payout
        req.reviewed_by = admin_user
        req.reviewed_at = timezone.now()
        req.save(update_fields=['status', 'payout', 'reviewed_by', 'reviewed_at'])
        return req


def reject(request_id, admin_user, reason):
    from app.models import VendorPayoutRequest
    reason = (reason or '').strip()[:200]
    if not reason:
        raise PayoutError('Reject karne ki wajah likhen (vendor ko dikhai jaye gi).')
    with transaction.atomic():
        req = VendorPayoutRequest.objects.select_for_update().get(pk=request_id)
        if req.status != 'pending':
            raise PayoutError('Ye request pehle hi nipat chuki hai.')
        req.status = 'rejected'
        req.reject_reason = reason
        req.reviewed_by = admin_user
        req.reviewed_at = timezone.now()
        req.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at'])
        return req
