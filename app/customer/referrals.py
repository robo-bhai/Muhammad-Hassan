"""Customer referral - dost ko bulao, dono ko wallet reward.

Tarteeb:
    1. Customer ka apna code hota hai (CustomerProfile.referral_code, 8 harf).
    2. Dost link /shop/r/<code>/ se aata hai -> code session me rakha jata hai (remember_code).
    3. Dost register karta hai -> create_pending() Referral (status 'pending') banata hai.
    4. Dost ka PEHLA order delivered ho (aur minimum amount ka ho) -> award_for_order() dono ko wallet credit deta hai.

Wallet par (order, kind) unique hai, is liye do alag kind: 'referral' (referrer) aur 'refbonus' (referee).

Is module ki koi bhi public function registration ya order ki status tabdeeli ko kabhi nahi rokti:
galti ho to log hoti hai aur None wapas aata hai.

Fraud ke checks (Step 6) award_for_order me `_blocked_reason()` se chalte hain. Do qism ke nateeje:
    HOLD   - abhi reward nahi, Referral 'pending' hi rahe (referee ka phone abhi verify nahi hua).
    REJECT - Referral 'rejected' mark hota hai, wajah (reject_reason) ke sath (khud ko refer, referrer ka account
             band, same phone / address / device, referrer ka mahine ka cap poora).
Reward sirf wallet me jata hai (cash nahi nikal sakta).
"""
import hashlib
import hmac
import logging
import re
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from ..shop_flags import shop_flag
from .offers import CENT, DONE_STATUSES, ZERO, referral_settings, wallet_enabled

logger = logging.getLogger(__name__)

SESSION_KEY = 'referral_code'
CODE_RE = re.compile(r'^[A-HJ-NP-Z2-9]{8}$')      # models.REFERRAL_ALPHABET ke mutabiq (0/O/1/I nahi)


# ---------------------------------------------------------------- code
def normalize_code(raw):
    """Spaces hatao, bara (upper) karo. Format galat ho to '' (kuch dhoondne ki zaroorat nahi)."""
    code = re.sub(r'\s+', '', str(raw or '')).upper()
    return code if CODE_RE.match(code) else ''


def enabled():
    """Referral chalu hai? (flag ON aur Wallet ON, kyun ke reward wallet me jata hai)."""
    return shop_flag('shop_referral_enabled') and wallet_enabled()


def ensure_code(customer):
    """Customer ka referral code do (na ho to bana do). Portal profile na ho (jaise POS customer) to None."""
    if customer is None:
        return None
    from ..models import CustomerProfile
    profile = CustomerProfile.objects.filter(customer=customer).first()
    if profile is None:
        return None
    try:
        return profile.ensure_referral_code()
    except Exception:
        logger.exception('referral: ensure_code failed (customer %s)', getattr(customer, 'pk', None))
        return None


def find_referrer(code):
    """Code se referrer Customer. Na-maujood ya galat code -> None."""
    code = normalize_code(code)
    if not code:
        return None
    from ..models import CustomerProfile
    profile = CustomerProfile.objects.select_related('customer').filter(referral_code=code).first()
    return profile.customer if profile else None


# ---------------------------------------------------------------- session
def remember_code(request, raw_code):
    """Link se aaya code session me rakho. Sahi format ho to True."""
    code = normalize_code(raw_code)
    if not code:
        return False
    request.session[SESSION_KEY] = code
    return True


def session_code(request):
    return normalize_code(request.session.get(SESSION_KEY, '')) if hasattr(request, 'session') else ''


def clear_session_code(request):
    try:
        request.session.pop(SESSION_KEY, None)
    except Exception:
        pass


# ---------------------------------------------------------------- device hash
def device_hash(request):
    """IP + browser (user-agent) ka HMAC hash. Asal IP kahin save nahi hota."""
    if request is None:
        return ''
    try:
        from .views_customer_auth import get_client_ip      # der se import: views is module ko bulate hain
        ip = get_client_ip(request) or ''
        ua = request.META.get('HTTP_USER_AGENT', '')[:300]
        key = str(settings.SECRET_KEY).encode()
        return hmac.new(key, f'{ip}|{ua}'.encode(), hashlib.sha256).hexdigest()
    except Exception:
        logger.exception('referral: device_hash failed')
        return ''


# ---------------------------------------------------------------- register
def create_pending(referee_customer, code, request=None):
    """Naye customer ke liye 'pending' Referral banao. Kuch bhi theek na ho to chup-chaap None:
    flag band, code khali / galat / na-maujood, khud ko refer, ya is customer ka Referral pehle se hai.
    Savepoint ke andar chalta hai, is liye bahar wali registration transaction kabhi kharab nahi hoti."""
    try:
        if referee_customer is None or not enabled():
            return None
        referrer = find_referrer(code)
        if referrer is None or referrer.pk == referee_customer.pk:
            return None
        from ..models import Referral
        if Referral.objects.filter(referee=referee_customer).exists():
            return None
        try:
            with transaction.atomic():
                return Referral.objects.create(referrer=referrer, referee=referee_customer,
                                               device_hash=device_hash(request))
        except IntegrityError:          # do jagah se ek saath: pehla rahega
            return None
    except Exception:
        logger.exception('referral: create_pending failed (referee %s)', getattr(referee_customer, 'pk', None))
        return None


# ---------------------------------------------------------------- reward
def _is_first_delivered_order(order):
    """Kya yeh referee ka pehla delivered order hai? (koi doosra delivered order pehle se nahi.)"""
    from ..models import SaleOrder
    return not (SaleOrder.objects.filter(customer_id=order.customer_id, status__in=DONE_STATUSES)
                .exclude(pk=order.pk).exists())


# ---------------------------------------------------------------- fraud checks
HOLD = 'hold'          # reward abhi nahi, Referral pending rahe
REJECT = 'reject'      # Referral rejected mark ho, wajah ke sath

MIN_ADDRESS_LEN = 12   # isse chhota address (jaise "ghar") match ke liye kaafi nahi


def phone_key(raw):
    """Phone ke aakhri 10 digit (+92 / 0 / spaces ka farq khatam). 7 se kam digit ho to '' (match nahi)."""
    digits = re.sub(r'\D', '', str(raw or ''))
    return digits[-10:] if len(digits) >= 7 else ''


def address_key(raw):
    """Address ko muqabla karne layak banao: chhote harf, sirf harf/ankre, ek space. Bohat chhota ho to ''."""
    text = re.sub(r'[\W_]+', ' ', str(raw or '').lower(), flags=re.UNICODE).strip()
    return text if len(text) >= MIN_ADDRESS_LEN else ''


def month_start(dt=None):
    """Maujooda (local) mahine ki pehli tareekh, 00:00."""
    dt = dt or timezone.now()
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _phones(customer):
    """Customer ke saare maloom phone (contact number + saved addresses ke phone / alternate phone)."""
    from ..models import CustomerAddress
    found = {phone_key(customer.contact_number)}
    for phone, alt in CustomerAddress.objects.filter(customer=customer).values_list('phone', 'alternate_phone'):
        found.add(phone_key(phone))
        found.add(phone_key(alt))
    found.discard('')
    return found


def _addresses(customer):
    """Customer ke saare maloom address (profile address + saved delivery addresses), muqable ki shakl me."""
    from ..models import CustomerAddress
    found = {address_key(customer.address)}
    for addr in CustomerAddress.objects.filter(customer=customer):     # address encrypted hai: Python me match
        found.add(address_key(f'{addr.address_line_1} {addr.address_line_2 or ""} {addr.city}'))
        found.add(address_key(f'{addr.address_line_1} {addr.city}'))
    found.discard('')
    return found


def _same_device(referral):
    """Isi referrer ka koi aur Referral, ya referrer ka apna (jab woh khud refer hua tha) isi device hash par?"""
    from ..models import Referral
    if not referral.device_hash:
        return False
    same = Referral.objects.filter(device_hash=referral.device_hash).exclude(pk=referral.pk)
    return (same.filter(referrer_id=referral.referrer_id).exists()
            or same.filter(referee_id=referral.referrer_id).exists())


def _referrer_active(referrer):
    """Referrer ka login account band (is_active=False) na ho. Portal user na ho to band nahi maana jata."""
    from ..models import CustomerProfile
    profile = CustomerProfile.objects.select_related('user').filter(customer=referrer).first()
    if profile is None:
        return False
    return profile.user is None or bool(profile.user.is_active)


def _month_used(referrer):
    """Is mahine referrer ko referral se kitna mil chuka (sirf 'rewarded')."""
    from ..models import Referral
    total = (Referral.objects.filter(referrer=referrer, status='rewarded', rewarded_at__gte=month_start())
             .aggregate(t=Sum('referrer_amount'))['t'])
    return Decimal(total or 0)


def _blocked_reason(referral, order, cfg):
    """Reward na dene ki wajah: (HOLD | REJECT, text), ya None agar sab theek.

    Tarteeb: khud ko refer -> referrer ka account -> referee ka phone verify -> same phone -> same address ->
    same device -> referrer ka mahine ka cap. Isko award_for_order ki transaction ke andar bulao
    (referrer ka cap ginte waqt uski Customer row lock hoti hai).
    """
    referrer, referee = referral.referrer, referral.referee
    if referrer.pk == referee.pk:
        return REJECT, 'Khud ko refer kiya'
    if not _referrer_active(referrer):
        return REJECT, 'Referrer ka account active nahi'
    from ..models import CustomerProfile
    if not CustomerProfile.objects.filter(customer=referee, phone_verified=True).exists():
        return HOLD, 'Referee ka phone verify nahi hua'
    if _phones(referrer) & _phones(referee):
        return REJECT, 'Same phone number'
    if _addresses(referrer) & _addresses(referee):
        return REJECT, 'Same address'
    if _same_device(referral):
        return REJECT, 'Same device (IP + browser)'
    if cfg['monthly_cap'] > 0:
        from ..models import Customer
        Customer.objects.select_for_update().filter(pk=referrer.pk).first()      # do referral ek saath cap na torain
        if _month_used(referrer) + cfg['referrer_reward'].quantize(CENT) > cfg['monthly_cap']:
            return REJECT, 'Referrer ka mahine ka cap poora'
    return None


def _reject(referral, reason):
    referral.status = 'rejected'
    referral.reject_reason = str(reason)[:120]
    referral.save(update_fields=['status', 'reject_reason'])


def _credit(customer, amount, kind, order, note):
    from ..models import WalletTransaction
    if amount <= 0:
        return None
    obj, _ = WalletTransaction.objects.get_or_create(
        order=order, kind=kind,
        defaults={'customer': customer, 'amount': amount, 'note': note})
    return obj


def _grant(referral, order, cfg):
    """Dono ko wallet credit (referral / refbonus) aur Referral ko 'rewarded' karo.
    Caller ki transaction aur Referral row lock ke andar chalao. Wallet credit (order, kind) par idempotent hai."""
    ref_amt = cfg['referrer_reward'].quantize(CENT)
    new_amt = cfg['referee_reward'].quantize(CENT)
    _credit(referral.referrer, ref_amt, 'referral', order,
            f'Referral: dost (customer #{referral.referee_id}) ka pehla order #{order.order_no}')
    _credit(referral.referee, new_amt, 'refbonus', order,
            f'Referral welcome bonus: order #{order.order_no}')
    referral.status = 'rewarded'
    referral.reject_reason = ''
    referral.reward_order = order
    referral.referrer_amount = ref_amt if ref_amt > 0 else ZERO
    referral.referee_amount = new_amt if new_amt > 0 else ZERO
    referral.rewarded_at = timezone.now()
    referral.save(update_fields=['status', 'reject_reason', 'reward_order', 'referrer_amount',
                                 'referee_amount', 'rewarded_at'])
    return referral


def award_for_order(order):
    """Delivered order par referral reward. Referral wapas (rewarded) ya None.

    Shartein: flag + wallet ON, order delivered, referee ka Referral 'pending', yeh referee ka PEHLA delivered
    order ho, total (coupon ke baad) minimum se kam na ho aur fraud checks (_blocked_reason) pass hon.
    Dono ko wallet credit (referral / refbonus).
    Poora kaam transaction.atomic me aur Referral row lock ke sath, is liye ek referral ka reward do dafa nahi hota.
    Order ki status tabdeeli ko yeh kabhi nahi rokta (galti sirf log hoti hai).
    """
    try:
        if order is None or not order.customer_id or order.status not in DONE_STATUSES or not enabled():
            return None
        from ..models import Referral
        # sasta pehla check (lock ke baghair): is customer ko kisi ne bulaya hi nahi to yahin khatam
        if not Referral.objects.filter(referee_id=order.customer_id, status='pending').exists():
            return None
        cfg = referral_settings()
        if cfg['referrer_reward'] <= 0 and cfg['referee_reward'] <= 0:
            return None
        with transaction.atomic():
            referral = (Referral.objects.select_for_update()
                        .filter(referee_id=order.customer_id, status='pending').first())
            if referral is None:                     # kisi aur ne abhi reward de diya
                return None
            if not _is_first_delivered_order(order):
                return None
            if Decimal(order.total_after_discount() or 0) < cfg['min_order']:
                return None
            blocked = _blocked_reason(referral, order, cfg)
            if blocked:
                action, reason = blocked
                if action == REJECT:                 # status 'rejected' + wajah save; HOLD me pending hi rehta hai
                    _reject(referral, reason)
                    logger.info('referral %s rejected: %s', referral.pk, reason)
                return None
            return _grant(referral, order, cfg)
    except Exception:
        logger.exception('referral: award_for_order failed (order %s)', getattr(order, 'pk', None))
        return None


# ---------------------------------------------------------------- customer UI (account page ka 'Dost ko bulao' card)
def whatsapp_url(link, company_name, referee_reward=ZERO, min_order=ZERO):
    """wa.me share link, pehle se likhe hue paigham ke sath (paigham me link aur, agar ho, welcome bonus)."""
    from urllib.parse import quote
    name = (company_name or 'our shop').strip() or 'our shop'
    text = f'Assalam o Alaikum! {name} se online order karen'
    if referee_reward and referee_reward > 0:
        text += f' aur apne pehle order (Rs. {min_order:,.0f} ya zyada) par Rs. {referee_reward:,.0f} ka welcome bonus payen'
    text += f'. Mera link: {link}'
    return 'https://wa.me/?text=' + quote(text, safe='')


def referral_card(request, customer, company_name=''):
    """Account page ke liye card ka data. None agar referral band hai, ya customer ka portal profile nahi.

    {'code', 'link', 'whatsapp_url', 'referrer_reward', 'referee_reward', 'min_order',
     'invited', 'pending', 'rewarded', 'rejected', 'earned'}
    earned = is customer ke 'referral' kind wale wallet credits ka jod (refbonus yahan nahi ginta).
    """
    if customer is None or not enabled():
        return None
    code = ensure_code(customer)
    if not code:
        return None
    from django.db.models import Count
    from django.urls import reverse
    from ..models import Referral, WalletTransaction
    cfg = referral_settings()
    counts = {row['status']: row['n'] for row in
              Referral.objects.filter(referrer=customer).values('status').annotate(n=Count('id'))}
    earned = WalletTransaction.objects.filter(customer=customer, kind='referral').aggregate(t=Sum('amount'))['t']
    link = request.build_absolute_uri(reverse('referral_landing', args=[code]))
    return {
        'code': code,
        'link': link,
        'whatsapp_url': whatsapp_url(link, company_name, cfg['referee_reward'], cfg['min_order']),
        'referrer_reward': cfg['referrer_reward'],
        'referee_reward': cfg['referee_reward'],
        'min_order': cfg['min_order'],
        'invited': sum(counts.values()),
        'pending': counts.get('pending', 0),
        'rewarded': counts.get('rewarded', 0),
        'rejected': counts.get('rejected', 0),
        'earned': Decimal(earned or 0).quantize(CENT),
    }


def award_on_phone_verified(customer):
    """Phone abhi verify hua. Agar referee ka pehla order pehle hi delivered ho chuka tha aur reward sirf
    phone verify na hone ki wajah se ruka hua tha, to ab reward do (sab checks award_for_order dobara chalata hai).
    Referral nahi / koi delivered order nahi / flag band ho to kuch nahi hota. Verify ke kaam ko kabhi nahi rokta."""
    try:
        if customer is None or not enabled():
            return None
        from ..models import Referral, SaleOrder
        if not Referral.objects.filter(referee=customer, status='pending').exists():
            return None
        order = (SaleOrder.objects.filter(customer=customer, status__in=DONE_STATUSES)
                 .order_by('order_date', 'pk').first())
        return award_for_order(order) if order is not None else None
    except Exception:
        logger.exception('referral: award_on_phone_verified failed (customer %s)', getattr(customer, 'pk', None))
        return None


# ---------------------------------------------------------------- admin ke haath se faisla
class ReferralActionError(Exception):
    """Admin ko seedha dikhai jane wali wajah."""


def manual_approve(referral_id):
    """Admin ka 'approve': fraud checks, minimum amount aur mahine ka cap nazar-andaz, reward de do.
    Phir bhi zaroori: referral / wallet ON, referee ka koi delivered order ho (reward usi order se bandha hota hai),
    khud ko refer na ho, aur reward pehle na mil chuka ho. Referee ka SAB SE PEHLA delivered order reward order banta hai."""
    from ..models import Referral, SaleOrder
    if not enabled():
        raise ReferralActionError('Referral ya Wallet band hai (Settings > Shop).')
    cfg = referral_settings()
    if cfg['referrer_reward'] <= 0 and cfg['referee_reward'] <= 0:
        raise ReferralActionError('Dono reward 0 hain (Settings > Shop).')
    with transaction.atomic():
        referral = Referral.objects.select_for_update().select_related('referrer', 'referee').get(pk=referral_id)
        if referral.status == 'rewarded':
            raise ReferralActionError('Reward pehle hi mil chuka hai.')
        if referral.referrer_id == referral.referee_id:
            raise ReferralActionError('Khud ko refer karne par reward nahi ho sakta.')
        order = (SaleOrder.objects.filter(customer_id=referral.referee_id, status__in=DONE_STATUSES)
                 .order_by('order_date', 'pk').first())
        if order is None:
            raise ReferralActionError('Referee ka abhi koi delivered order nahi.')
        return _grant(referral, order, cfg)
