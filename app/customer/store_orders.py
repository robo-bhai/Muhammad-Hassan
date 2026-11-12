"""
Step 2 - Multi-vendor cart aur vendor ke orders.

Is file mein 2 hisse hain:

A) CART RULES  (customer side)
   - cart mein ek waqt ek hi store ka maal (store = vendor, ya vendor_id=0 matlab shop ka apna maal)
   - store ki delivery fee, minimum order aur open/closed checkout mein lagte hain

B) VENDOR ORDER ACTIONS  (vendor side)
   - naya order aane par vendor ko notification
   - Accept / Reject / Ready
   - Reject par customer ko wajah ke saath notification + refund note + doosre stores ke suggestions

Order ka status purane SaleOrder statuses se hi chalta hai (admin ka kaam waise hi chalta rahe):
    pending   -> vendor ke liye "New"
    confirmed -> Accepted (tayyar ho raha hai)
    ready     -> Ready (rider/customer ke liye tayyar)
    delivered -> Deliver ho gaya (vendor khud mark karta hai; cash mil gaya)
    cancelled -> Rejected (reject_reason ke saath)
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils.timezone import now

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')

# Vendor reject karte waqt in mein se wajah chunta hai
REJECT_REASONS = [
    ('out_of_stock', 'Item is out of stock'),
    ('store_busy', 'Store is very busy right now'),
    ('store_closed', 'Store is closing'),
    ('out_of_area', 'We do not deliver to your area'),
    ('price_issue', 'Item price or details are wrong'),
    ('other', 'Other reason'),
]
REJECT_REASON_LABELS = dict(REJECT_REASONS)

# vendor action -> (status se, status par, naya status)
ACTIONS = {
    'accept': (('pending',), 'confirmed'),
    'reject': (('pending',), 'cancelled'),
    'ready': (('confirmed', 'processing'), 'ready'),
    'delivered': (('ready',), 'delivered'),
    # system action: vendor ne waqt par jawab nahi diya -> order khud cancel (user=None)
    'expire': (('pending',), 'cancelled'),
}


# ============================================================
# A) CART RULES
# ============================================================

def _vendor_ids_in_cart(cart):
    """Cart ke items kin stores ke hain. 0 = shop ka apna maal. Purane session items (vendor_id ke baghair) DB se."""
    ids = set()
    missing = []
    for item in (cart or {}).values():
        if 'vendor_id' in item:
            ids.add(int(item.get('vendor_id') or 0))
        elif item.get('product_id'):
            missing.append(item['product_id'])
    if missing:
        from ..models import Product
        for vid in Product.objects.filter(pk__in=missing).values_list('vendor_id', flat=True):
            ids.add(int(vid or 0))
    return ids


def cart_store_id(cart):
    """Cart ka store id (0 = shop). Cart khali ho to None."""
    ids = _vendor_ids_in_cart(cart)
    return sorted(ids)[0] if ids else None


def get_store_profile(vendor_id):
    """vendor_id ka VendorProfile (ya None: shop ka apna maal / profile nahi)."""
    if not vendor_id:
        return None
    from ..models import VendorProfile
    return VendorProfile.objects.filter(vendor_id=vendor_id).first()


def store_name(vendor_id):
    """Customer ko dikhane wala store ka naam."""
    prof = get_store_profile(vendor_id)
    if prof:
        return prof.business_name
    from ..models import CompanyInfo
    company = CompanyInfo.objects.first()
    return company.name if company else 'Shop'


def cart_store_rules(cart, subtotal):
    """
    Cart ke store ke qaide: delivery fee, minimum order, open/closed.

    Shop ke apne maal (vendor_id=0) par kuch nahi lagta - purana delivery system chalta hai.
    """
    ids = _vendor_ids_in_cart(cart)
    vendor_id = sorted(ids)[0] if ids else 0
    prof = get_store_profile(vendor_id)
    subtotal = Decimal(str(subtotal or 0))
    rules = {
        'vendor_id': vendor_id,
        'is_vendor_store': prof is not None,
        'mixed': len(ids) > 1,
        'profile': prof,
        'name': prof.business_name if prof else store_name(0),
        'delivery_fee': ZERO,
        'min_order': ZERO,
        'min_ok': True,
        'short_by': ZERO,
        'is_open': True,
        'closed_message': '',
        'time_text': '',
        'distance_km': None,
        'area_extra': ZERO,
        'out_of_range': False,
        'range_message': '',
        'fee_dynamic': False,
    }
    if prof is None:
        return rules

    min_order = Decimal(prof.min_order_amount or 0)
    from . import delivery_pricing
    q = delivery_pricing.quote(prof)
    rules.update({
        'delivery_fee': q['fee'],
        'distance_km': q['distance_km'],
        'area_extra': q['area_extra'],
        'out_of_range': q['out_of_range'],
        'range_message': q['message'],
        'fee_dynamic': q['dynamic'],
        'min_order': min_order,
        'min_ok': subtotal >= min_order,
        'short_by': max(min_order - subtotal, ZERO),
        'is_open': prof.is_open_now,
        'time_text': f"{prof.delivery_time_min}-{prof.delivery_time_max} min",
    })
    if not prof.is_open_now:
        rules['closed_message'] = f'{prof.business_name} abhi band hai, baad mein order karein.'
    return rules


def vendor_delivery_info(rules):
    """calculate_delivery_charges jaisa dict, par store ki apni fee ke sath."""
    fee = rules['delivery_fee']
    return {
        'charges': fee,
        'type': 'standard',
        'time_estimate': rules['time_text'],
        'message': (f"🚚 {rules['name']} delivery" +
                    (f" · {rules['distance_km']} km" if rules.get('distance_km') is not None else '')),
        'is_free': fee <= 0,
    }


def vendor_delivery_options(rules):
    info = vendor_delivery_info(rules)
    return [{
        'type': 'standard',
        'label': f"🚚 {rules['name']} Delivery",
        'charges': info['charges'],
        'time': info['time_estimate'],
        'is_free': info['is_free'],
        'is_default': True,
    }]


# ------------------------------------------------------------
# SCHEDULED ORDERS (baad ke waqt ke liye order)
# ------------------------------------------------------------
SCHEDULE_MIN_MINUTES = 30      # kam az kam itne minute baad ka waqt
SCHEDULE_MAX_DAYS = 7          # zyada se zyada itne din aage
SCHEDULE_LEAD_MINUTES = 60     # vendor ke accept ki ghari waqt se itne minute pehle shuru hoti hai
SCHEDULE_SESSION_KEY = 'scheduled_for'


def parse_schedule(raw):
    """datetime-local '2026-11-10T19:30' (ya ISO) -> aware datetime. Khali -> None. Kharab -> ValueError."""
    from datetime import datetime
    from django.utils import timezone
    raw = (raw or '').strip()
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def session_schedule(session):
    """Session mein rakha hua schedule (aware datetime) ya None."""
    try:
        return parse_schedule(session.get(SCHEDULE_SESSION_KEY))
    except (ValueError, TypeError):
        return None


def _within_hours_at(prof, local_time):
    if not prof.opens_at or not prof.closes_at:
        return True
    if prof.opens_at <= prof.closes_at:
        return prof.opens_at <= local_time <= prof.closes_at
    return local_time >= prof.opens_at or local_time <= prof.closes_at


def schedule_error(cart, when, subtotal=0):
    """Schedule ka waqt theek na ho to message (str), warna None."""
    from django.utils import timezone
    n = now()
    if when < n + timedelta(minutes=SCHEDULE_MIN_MINUTES):
        return f'Schedule ka waqt kam az kam {SCHEDULE_MIN_MINUTES} minute baad ka chunein.'
    if when > n + timedelta(days=SCHEDULE_MAX_DAYS):
        return f'Schedule {SCHEDULE_MAX_DAYS} din se zyada aage ka nahi ho sakta.'
    rules = cart_store_rules(cart, subtotal)
    prof = rules.get('profile')
    if rules.get('is_vendor_store') and prof:
        if prof.store_status == 'closed':
            return f"{rules['name']} abhi band hai, schedule order nahi ho sakta."
        if not _within_hours_at(prof, timezone.localtime(when).time()):
            return (f"{rules['name']} us waqt band hoga. Khulne ka waqt: "
                    f"{prof.opens_at.strftime('%I:%M %p')} - {prof.closes_at.strftime('%I:%M %p')}.")
    return None


def validate_cart_for_order(cart, subtotal, scheduled_for=None):
    """Order se pehle check. Masla ho to message (str) lautata hai, theek ho to None.
    scheduled_for dein to store ke abhi khule hone ki shart nahi, schedule ke waqt ki jaanch hoti hai."""
    rules = cart_store_rules(cart, subtotal)
    if rules['mixed']:
        return 'Your cart has items from different stores. Empty the cart and order from one store.'
    if scheduled_for is not None:
        err = schedule_error(cart, scheduled_for, subtotal)
        if err:
            return err
    if rules['is_vendor_store']:
        if rules.get('out_of_range'):
            return rules['range_message']
        if scheduled_for is None and not rules['is_open']:
            return rules['closed_message']
        if not rules['min_ok']:
            return (f"{rules['name']} ka minimum order Rs. {rules['min_order']:,.0f} hai. "
                    f"Aur Rs. {rules['short_by']:,.0f} ka maal add karein.")
    return None


def store_order_fields(cart, cart_data, payment_method):
    """SaleOrder.objects.create(...) mein lagane wali store ki fields."""
    rules = cart_data.get('store') or cart_store_rules(cart, cart_data.get('subtotal', 0))
    prof = rules.get('profile')
    return {
        'vendor': prof.vendor if prof else None,
        'delivery_fee': cart_data.get('delivery_charges') or ZERO,
        'payment_method': payment_method or '',
    }


# ------------------------------------------------------------
# STOCK LOCK  (overselling roknay ke liye)
# ------------------------------------------------------------
# Jin orders ka maal abhi tak invoice (stock kam) nahi hua, magar customer ko de diya gaya hai.
OPEN_ORDER_STATUSES = ('pending', 'confirmed', 'processing', 'ready')


def check_and_lock_stock(cart, warehouse):
    """
    Order se pehle stock check + lock. Sirf transaction.atomic ke ANDAR chalayein.

    - Cart ke har product ki Inventory row select_for_update se lock hoti hai (product_id ki
      tarteeb mein, taake do orders aapas mein deadlock na karein). Lock transaction ke aakhir
      tak rehta hai, yani doosra customer tab tak intezar karta hai jab tak pehla order ban jaye.
    - Available = stock - admin reserved_stock - un khule web orders ki qty jo abhi invoice nahi
      hue (stock invoice par kam hota hai, is liye pending orders alag se ginay jate hain).
    - Cart mein ek product kayi baar ho to qty jama karke check hoti hai.

    Return: None (sab theek) ya error text (customer ko dikhane ke liye).
    """
    from django.db.models import Sum
    from ..models import Inventory, SaleOrderItem

    need = {}
    names = {}
    for item in (cart or {}).values():
        pid = item['product_id']
        need[pid] = need.get(pid, 0) + item['quantity']
        names.setdefault(pid, item.get('name') or f'#{pid}')

    pids = sorted(need)
    locked = {
        inv.product_id: inv
        for inv in Inventory.objects.select_for_update()
        .filter(warehouse=warehouse, product_id__in=pids).order_by('product_id')
    }

    for pid in pids:
        inv = locked.get(pid)
        stock = (inv.stock or 0) if inv else 0
        reserved = (inv.reserved_stock or 0) if inv else 0
        # reserved=True wali items already reserved_stock mein hain: double count na karein
        committed = SaleOrderItem.objects.filter(
            order__warehouse=warehouse, product_id=pid, reserved=False,
            order__status__in=OPEN_ORDER_STATUSES, order__converted_to_sale__isnull=True,
        ).aggregate(t=Sum('qty'))['t'] or 0
        available = stock - reserved - committed
        if need[pid] > available:
            return f'Not enough stock for {names[pid]}. Available: {max(0, int(available))}'
    return None


# ============================================================
# B) VENDOR ORDER ACTIONS
# ============================================================

def order_payable_total(order):
    """Items + delivery fee - discount."""
    return order.total_after_discount() + (order.delivery_fee or ZERO)


def order_cash_due(order):
    """Customer se asal mein kitni raqam leni hai: total - wallet se ada hui raqam (rider COD yahi leta hai)."""
    return max(order_payable_total(order) - (getattr(order, 'wallet_paid', None) or ZERO), ZERO)


def _notify(user, title, message, link=None, kind='info'):
    if not user:
        return
    try:
        from ..models import Notification
        Notification.send(user=user, title=title, message=message,
                          notification_type=kind, category='sales', link=link)
    except Exception as exc:  # notification se order kabhi na rukey
        logger.error("Notification error: %s", exc)


def _customer_user(order):
    portal = getattr(order.customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def notify_vendor_new_order(order):
    """Naya order aane par vendor ko in-app notification (vendor dashboard/navbar mein)."""
    if not order.vendor_id:
        return
    prof = get_store_profile(order.vendor_id)
    if not prof:
        return
    items = order.items.count()
    when = ''
    if getattr(order, 'scheduled_for', None):
        from django.utils import timezone
        when = f"\n⏰ Schedule: {timezone.localtime(order.scheduled_for).strftime('%d %b, %I:%M %p')}"
    _notify(
        prof.user,
        f'🛒 Naya order #{order.order_no}' + (' (schedule)' if when else ''),
        (f'{order.customer.name} - {items} item(s)\n'
         f'Total: Rs. {order_payable_total(order):,.0f}{when}\n'
         f'Dashboard mein Accept ya Reject karein.'),
        link='/shop/vendor/orders/',
        kind='sale',
    )


def whatsapp_link(phone, text):
    """wa.me link (khud send nahi hota - vendor click karke bhejta hai)."""
    try:
        from ..whatsapp_utils import WhatsAppSender
        res = WhatsAppSender.send_direct_message(phone, text)
        return res.get('url') if res.get('success') else None
    except Exception:
        return None


def customer_whatsapp_text(order, action):
    shop = store_name(order.vendor_id)
    if action == 'accept':
        eta = f" Taqreeban {order.prep_minutes} minute mein tayyar hoga." if order.prep_minutes else ''
        return f"✅ {shop}: Aap ka order #{order.order_no} qubool ho gaya.{eta}"
    if action == 'ready':
        return f"📦 {shop}: Aap ka order #{order.order_no} tayyar hai."
    if action == 'delivered':
        return f"🎉 {shop}: Aap ka order #{order.order_no} deliver ho gaya. Shukriya!"
    if action in ('reject', 'expire'):
        return (f"❌ {shop}: Maazrat, order #{order.order_no} qubool nahi ho saka. "
                f"Wajah: {order.reject_reason}")
    return ''


def suggest_other_stores(order, limit=3):
    """
    Reject hone par naye stores: wahi category ka maal bechne wale, abhi khule hue.
    Pehle same category wale, phir koi bhi khula store.
    """
    from ..models import Product, VendorProfile

    live = Product.objects.filter(is_active=True, approval_status='approved', vendor__isnull=False)
    base = VendorProfile.objects.filter(
        is_approved=True, vendor__in=live.values('vendor')
    ).exclude(vendor_id=order.vendor_id).select_related('vendor')

    cat_ids = list(
        Product.objects.filter(saleorderitem__order=order)
        .exclude(category__isnull=True).values_list('category_id', flat=True).distinct()
    )
    picked, seen = [], set()
    if cat_ids:
        same = base.filter(vendor__in=live.filter(category_id__in=cat_ids).values('vendor'))
        for prof in same:
            if prof.is_open_now and prof.pk not in seen:
                picked.append(prof)
                seen.add(prof.pk)
    if len(picked) < limit:
        for prof in base:
            if prof.is_open_now and prof.pk not in seen:
                picked.append(prof)
                seen.add(prof.pk)
    return picked[:limit]


def refund_note(order):
    """Reject par paisa ka message. COD mein kuch kata hi nahi hota."""
    if (order.payment_method or 'cod') == 'cod':
        return 'It was Cash on Delivery, so no money was taken from you.'
    return ('Aap ne online payment ki thi to poori raqam wapas ki jayegi. '
            'If there is a problem with the refund, please contact us.')


class OrderActionError(Exception):
    """Vendor ke action mein masla (galat status, wajah nahi di, ...). Message customer-friendly hota hai."""


def clean_reject_reason(code, note):
    """Chuni hui wajah + optional note -> customer ko dikhane wala text (max 200 chars)."""
    code = (code or '').strip()
    label = REJECT_REASON_LABELS.get(code)
    note = (note or '').strip()
    if not label:
        raise OrderActionError('Choose a reason for rejecting.')
    if code == 'other':
        if not note:
            raise OrderActionError('If you choose "Other reason", please write the reason.')
        return note[:200]
    return (f'{label}. {note}' if note else label)[:200]


def apply_vendor_action(order, action, *, user, prep_minutes=None, reason_code='', reason_note=''):
    """
    Vendor ka action lagao. order select_for_update ke andar (transaction.atomic) hona chahiye.
    Nakaam hone par OrderActionError.
    """
    if action not in ACTIONS:
        raise OrderActionError('Invalid action.')
    allowed_from, new_status = ACTIONS[action]
    if order.status not in allowed_from:
        raise OrderActionError(
            f'Order #{order.order_no} ab "{order.get_status_display()}" hai, ye action nahi ho sakta.')

    if action == 'reject':
        order.reject_reason = clean_reject_reason(reason_code, reason_note)
    if action == 'accept':
        deadline = accept_deadline(order)
        if deadline and now() > deadline:
            raise OrderActionError(
                f'Order #{order.order_no} ka jawab dene ka waqt ({accept_timeout_minutes()} minute) khatam ho gaya. '
                'Order khud cancel ho raha hai.')
        if prep_minutes:
            order.prep_minutes = prep_minutes
    if action == 'expire':
        order.reject_reason = f'Store ne {accept_timeout_minutes()} minute mein jawab nahi diya.'[:200]

    order.status = new_status
    if action != 'expire':          # expire par vendor_responded_at khali rehta hai (miss hua order)
        order.vendor_responded_at = now()
    order.save()
    if action == 'delivered':
        auto_invoice_delivered(order, user)
    after_vendor_action(order, action, user)


def auto_invoice_delivered(order, user):
    """
    Delivered hote hi invoice (Sale) khud bana do, poora PAID (COD cash mil chuka / online pehle ada).
    Is se vendor dashboard ki sales/commission bharti hain, stock kam hota hai aur accounts ban jate hain.
    Kuch bhi fail ho (stock kam, month locked...) to delivery na ruke: order Delivered hi rehta hai
    aur admin ko notification milti hai ke manually invoice banaye.
    """
    from django.db import transaction
    from ..models import Sale, SaleItem
    from ..vendor_commission import option_sale_item_fields

    if order.converted_to_sale_id:
        return None
    try:
        with transaction.atomic():
            sale = Sale.objects.create(
                warehouse=order.warehouse,
                customer=order.customer,
                bill_no=f"INV-{order.order_no}",
                sale_date=now(),
                paid=Decimal('0.00'),
                discount_value=order.discount_value,
                created_by=user,
            )
            for item in order.items.all():
                SaleItem.objects.create(sale=sale, product=item.product, qty=item.qty, price=item.price,
                                        **option_sale_item_fields(item))
            # Poora paid: items ki raqam customer ne (COD cash / online) de di hai
            sale.paid = sale.total_amount()
            sale.save()
            order.status = 'invoiced'
            order.converted_to_sale = sale
            order.save()
        return sale
    except Exception as exc:
        logger.error("Auto invoice failed for order %s: %s", order.order_no, exc)
        try:
            from django.contrib.auth.models import User
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                _notify(admin, f'⚠️ Order #{order.order_no} ka invoice khud nahi bana',
                        f'Wajah: {exc}\nOrder Delivered hai, manually "Convert to Invoice" karein.',
                        f'/orders/sale/{order.id}/', 'warning')
        except Exception:
            pass
        return None


def after_vendor_action(order, action, user):
    """Customer (aur reject par admin) ko batao."""
    link = f'/shop/order/{order.id}/'
    cust_user = _customer_user(order)
    shop = store_name(order.vendor_id)

    if action == 'accept':
        eta = f'\nTayyar hone mein ~{order.prep_minutes} minute.' if order.prep_minutes else ''
        _notify(cust_user, f'✅ Order #{order.order_no} qubool ho gaya',
                f'{shop} ne aap ka order qubool kar liya.{eta}', link, 'success')
    elif action == 'ready':
        _notify(cust_user, f'📦 Order #{order.order_no} tayyar hai',
                f'{shop} ka maal tayyar hai.', link, 'info')
    elif action == 'delivered':
        _notify(cust_user, f'🎉 Order #{order.order_no} deliver ho gaya',
                f'{shop} ka order aap tak pahunch gaya. Shukriya!', link, 'success')
        try:
            from django.contrib.auth.models import User
            for admin in User.objects.filter(is_superuser=True, is_active=True):
                _notify(admin, f'✅ Order #{order.order_no} deliver ho gaya',
                        f'{shop} ne order deliver mark kiya. Rs. {order_payable_total(order):,.0f} '
                        f'({(order.payment_method or "cod").upper()}). '
                        + ('Invoice khud ban gaya.' if order.converted_to_sale_id else 'Ab invoice bana sakte hain.'),
                        f'/orders/sale/{order.id}/', 'success')
        except Exception as exc:
            logger.error("Delivered notify error: %s", exc)
    elif action in ('reject', 'expire'):
        if action == 'expire':
            _notify(cust_user, f'⏰ Order #{order.order_no} cancel ho gaya',
                    f'{shop} ne waqt par jawab nahi diya.\n{refund_note(order)}\nDoosre store se order kar sakte hain.',
                    link, 'warning')
            prof = get_store_profile(order.vendor_id)
            _notify(getattr(prof, 'user', None), f'⏰ Order #{order.order_no} miss ho gaya',
                    f'Aap ne {accept_timeout_minutes()} minute mein jawab nahi diya, order khud cancel ho gaya. '
                    'Naye orders par jaldi Accept ya Reject karein.',
                    '/shop/vendor/orders/?tab=done', 'warning')
        else:
            _notify(cust_user, f'❌ Order #{order.order_no} reject ho gaya',
                    f'{shop} ne order qubool nahi kiya.\nWajah: {order.reject_reason}\n{refund_note(order)}',
                    link, 'warning')
        # Online payment ho to admin ko refund yaad dilao
        if (order.payment_method or 'cod') != 'cod':
            try:
                from django.contrib.auth.models import User
                for admin in User.objects.filter(is_superuser=True, is_active=True):
                    _notify(admin, f'💰 Refund karna hai - #{order.order_no}',
                            f'{shop} ne order reject kiya ({order.reject_reason}).\n'
                            f'Payment: {order.payment_method}, Rs. {order_payable_total(order):,.0f}',
                            f'/orders/sale/{order.id}/', 'warning')
            except Exception as exc:
                logger.error("Refund notify error: %s", exc)



# ============================================================
# C) AUTO-EXPIRE (Talabat jaisa): vendor waqt par jawab na de to order cancel
# ============================================================

EXPIRE_THROTTLE_KEY = 'store_orders:expire_last_run'


def accept_timeout_minutes():
    """settings.VENDOR_ACCEPT_TIMEOUT_MINUTES (default 5). 0 = auto-expire band."""
    try:
        minutes = int(getattr(settings, 'VENDOR_ACCEPT_TIMEOUT_MINUTES', 5))
    except (TypeError, ValueError):
        minutes = 5
    return max(minutes, 0)


def accept_deadline(order):
    """Store order ke jawab ki aakhri waqt; baghair deadline wale order (shop ka apna, pending nahi, band) par None."""
    minutes = accept_timeout_minutes()
    if not minutes or not order.vendor_id or order.status != 'pending' or not order.created_at:
        return None
    start = order.created_at
    sched = getattr(order, 'scheduled_for', None)
    if sched:       # schedule order: ghari waqt se thora pehle shuru hoti hai
        start = max(start, sched - timedelta(minutes=SCHEDULE_LEAD_MINUTES))
    return start + timedelta(minutes=minutes)


def expire_unaccepted_orders(order_id=None):
    """
    Jin store orders ko vendor ne waqt par accept/reject nahi kiya unhein cancel karo
    (customer, vendor aur online payment mein admin ko notification ke saath).
    order_id dein to sirf wahi order check hota hai. Wapas: kitne order expire hue.
    """
    from django.db import transaction
    from ..models import SaleOrder

    minutes = accept_timeout_minutes()
    if not minutes:
        return 0
    cutoff = now() - timedelta(minutes=minutes)
    from django.db.models import Q
    due = SaleOrder.objects.filter(status='pending', vendor__isnull=False, created_at__lte=cutoff).filter(
        Q(scheduled_for__isnull=True)
        | Q(scheduled_for__lte=cutoff + timedelta(minutes=SCHEDULE_LEAD_MINUTES)))
    if order_id is not None:
        due = due.filter(pk=order_id)
    expired = 0
    for oid in list(due.values_list('id', flat=True)[:200]):
        try:
            with transaction.atomic():
                order = SaleOrder.objects.select_for_update().get(pk=oid)
                if order.status != 'pending':      # is dauran vendor ne jawab de diya
                    continue
                apply_vendor_action(order, 'expire', user=None)
                expired += 1
        except Exception as exc:
            logger.error("Order expire failed for %s: %s", oid, exc)
    return expired


def expire_if_due(throttle_seconds=15):
    """
    Cron ke baghair bhi chale: vendor/customer pages khulne par check (har ~15 second mein ek baar).
    Cron/command (expire_orders) laga hua ho to ye sirf extra hifazat hai.
    """
    try:
        if not cache.add(EXPIRE_THROTTLE_KEY, 1, throttle_seconds):
            return 0
    except Exception:
        pass
    return expire_unaccepted_orders()
