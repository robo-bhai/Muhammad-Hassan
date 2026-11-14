"""
Order chat: customer <-> vendor (store) aur customer <-> rider, har order ke andar.

- Channel 'vendor' : customer aur store ke beech (sirf store wale orders).
- Channel 'rider'  : customer aur us order ka rider (rider assign hone ke baad).
- Sirf us order ke asal fareeq (customer, store owner, assigned rider) dekh/likh sakte hain; baqi sab ko 403.
- Order khatam (delivered / cancelled) hone ke baad CLOSE_WINDOW_HOURS tak likha ja sakta hai, phir sirf parhna.
- Naya paigham aane par samne wale ko notification + push (2 minute mein ek dafa, spam se bachne ke liye).
- Admin switch: Settings > Shop > "Order chat" (shop_order_chat_enabled).
- Phone number nahi dikhaye jate: baat chit app ke andar hi hoti hai.
"""
import json
import logging
from datetime import timedelta

from django.db.models import Count
from .vendor_access import get_vendor_profile, profile_for_vendor
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from ..models import DeliveryInfo, Notification, OrderChatMessage, SaleOrder
from ..shop_flags import flag_required
from . import store_orders

logger = logging.getLogger(__name__)

CHANNELS = ('vendor', 'rider')
MAX_LEN = 1000
MAX_PER_MINUTE = 20                 # ek user, ek order par
CLOSE_WINDOW_HOURS = 2              # order khatam hone ke baad kitni der tak likh sakte hain
NOTIFY_GAP_MINUTES = 2
TERMINAL = ('delivered', 'invoiced', 'cancelled')
MESSAGES_LIMIT = 200


# ------------------------------------------------------------------ helpers
def _rider_delivery(order):
    return (DeliveryInfo.objects.filter(sale_order=order, rider__isnull=False)
            .select_related('rider', 'rider__user').first())


def _role_for(user, order):
    """-> 'customer' / 'vendor' / 'rider' / None (is order ka fareeq nahi)."""
    if not user.is_authenticated:
        return None
    cp = getattr(user, 'customer_profile', None)
    if cp is not None and getattr(cp, 'customer_id', None) == order.customer_id:
        return 'customer'
    if order.vendor_id and profile_for_vendor(user, order.vendor_id) is not None:
        return 'vendor'
    rp = getattr(user, 'rider_profile', None)
    if rp is not None and DeliveryInfo.objects.filter(sale_order=order, rider=rp).exists():
        return 'rider'
    return None


def _channels_for(role, order, di):
    """Is role ko kaun se channels dikhte hain."""
    if role == 'vendor':
        return ['vendor']
    if role == 'rider':
        return ['rider']
    out = []
    if order.vendor_id:
        out.append('vendor')
    if di is not None:
        out.append('rider')
    return out


def _is_open(order):
    if order.status not in TERMINAL:
        return True
    return timezone.now() - (order.updated_at or order.created_at) < timedelta(hours=CLOSE_WINDOW_HOURS)


def _counterpart_user(order, role, channel, di):
    """Paigham kisko jana chahiye (User)."""
    if role == 'customer':
        if channel == 'vendor':
            prof = store_orders.get_store_profile(order.vendor_id)
            return getattr(prof, 'user', None)
        return getattr(getattr(di, 'rider', None), 'user', None)
    portal = getattr(order.customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def _other_label(order, role, channel, di):
    if role == 'customer':
        if channel == 'vendor':
            return store_orders.store_name(order.vendor_id) or 'Store'
        return (getattr(getattr(di, 'rider', None), 'name', '') or 'Rider')
    first = (getattr(order.customer, 'name', '') or 'Customer').split(' ')[0]
    return first


def _link_for(recipient_role, order):
    if recipient_role == 'customer':
        return f'/shop/order/{order.pk}/'
    if recipient_role == 'vendor':
        return '/shop/vendor/orders/'
    return '/shop/rider/'


def _recipient_role(sender_role, channel):
    return channel if sender_role == 'customer' else 'customer'


def _context(request, order_id, channel):
    """-> (order, role, di, error_response). error_response None ho to sab theek."""
    order = get_object_or_404(SaleOrder.objects.select_related('customer'), pk=order_id)
    role = _role_for(request.user, order)
    if role is None:
        return order, None, None, JsonResponse({'success': False, 'message': 'Not allowed.'}, status=403)
    di = _rider_delivery(order)
    if channel not in _channels_for(role, order, di):
        return order, role, di, JsonResponse({'success': False, 'message': 'This chat is not available yet.'}, status=404)
    return order, role, di, None


def _serialize(msg, role):
    local = timezone.localtime(msg.created_at)
    return {'id': msg.pk, 'mine': msg.sender_role == role, 'text': msg.message,
            'time': local.strftime('%I:%M %p').lstrip('0'), 'day': local.strftime('%d %b')}


def _mark_read(order, channel, role):
    qs = OrderChatMessage.objects.filter(order=order, channel=channel)
    if role == 'customer':
        qs.exclude(sender_role='customer').filter(read_by_customer=False).update(read_by_customer=True)
    else:
        qs.filter(sender_role='customer', read_by_other=False).update(read_by_other=True)


def _notify(order, sender_role, channel, text, di):
    try:
        rec_role = _recipient_role(sender_role, channel)
        user = _counterpart_user(order, sender_role, channel, di)
        if not user:
            return
        who = {'customer': 'Customer', 'vendor': 'Store', 'rider': 'Rider'}[sender_role]
        title = f'\U0001F4AC {who} - Order #{order.order_no}'
        since = timezone.now() - timedelta(minutes=NOTIFY_GAP_MINUTES)
        if Notification.objects.filter(user=user, title=title, created_at__gte=since).exists():
            return
        store_orders._notify(user, title, text[:140], link=_link_for(rec_role, order), kind='info')
    except Exception:       # notification ki kisi galti se chat kabhi na rukey
        logger.exception('Order chat notify failed (order=%s)', getattr(order, 'pk', None))


# ------------------------------------------------------------------ views
@require_GET
@flag_required('shop_order_chat_enabled', json=True)
def order_chat_messages(request, order_id, channel):
    """GET ?after=<id> : naye paigham (pehli dafa after na do: aakhri MESSAGES_LIMIT)."""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'login': True}, status=401)
    order, role, di, err = _context(request, order_id, channel)
    if err:
        return err
    try:
        after = int(request.GET.get('after') or 0)
    except ValueError:
        after = 0
    qs = OrderChatMessage.objects.filter(order=order, channel=channel)
    if after:
        rows = list(qs.filter(pk__gt=after).order_by('id')[:MESSAGES_LIMIT])
    else:
        rows = list(qs.order_by('-id')[:MESSAGES_LIMIT])[::-1]
    _mark_read(order, channel, role)
    can_write = _is_open(order)
    resp = JsonResponse({
        'success': True,
        'messages': [_serialize(m, role) for m in rows],
        'can_write': can_write,
        'closed_note': '' if can_write else 'This order is closed, so chat is read-only now.',
        'title': _other_label(order, role, channel, di),
        'order_no': order.order_no,
    })
    resp['Cache-Control'] = 'no-store'
    return resp


@require_POST
@flag_required('shop_order_chat_enabled', json=True)
def order_chat_send(request, order_id, channel):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'login': True}, status=401)
    order, role, di, err = _context(request, order_id, channel)
    if err:
        return err
    if not _is_open(order):
        return JsonResponse({'success': False, 'message': 'This order is closed, so chat is read-only now.'}, status=403)
    try:
        text = (json.loads(request.body or b'{}').get('message') if request.content_type == 'application/json'
                else request.POST.get('message')) or ''
    except (ValueError, AttributeError):
        text = ''
    text = str(text).strip()
    if not text:
        return JsonResponse({'success': False, 'message': 'Write a message first.'}, status=400)
    if len(text) > MAX_LEN:
        return JsonResponse({'success': False, 'message': f'Message is too long (max {MAX_LEN} characters).'}, status=400)
    recent = OrderChatMessage.objects.filter(order=order, sender=request.user,
                                             created_at__gte=timezone.now() - timedelta(minutes=1)).count()
    if recent >= MAX_PER_MINUTE:
        return JsonResponse({'success': False, 'message': 'Too many messages. Please wait a moment.'}, status=429)

    msg = OrderChatMessage.objects.create(
        order=order, channel=channel, sender_role=role, sender=request.user, message=text,
        read_by_customer=(role == 'customer'), read_by_other=(role != 'customer'))
    _notify(order, role, channel, text, di)
    return JsonResponse({'success': True, 'message': _serialize(msg, role)})


@require_GET
@flag_required('shop_order_chat_enabled', json=True)
def order_chat_unread(request):
    """Mere liye parhe nahi gaye paigham: {'orders': {order_id: {'vendor': n, 'rider': n}}, 'total': n}.
    Customer: apne orders | vendor: apne store ke orders | rider: apne assigned orders."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'login': True}, status=401)
    base = OrderChatMessage.objects.all()
    cp = getattr(user, 'customer_profile', None)
    vp = get_vendor_profile(user)
    rp = getattr(user, 'rider_profile', None)
    if cp is not None and getattr(cp, 'customer_id', None):
        qs = base.filter(order__customer_id=cp.customer_id, read_by_customer=False).exclude(sender_role='customer')
    elif vp is not None and getattr(vp, 'vendor_id', None):
        from .vendor_access import accessible_profiles
        qs = base.filter(order__vendor_id__in=[p.vendor_id for p in accessible_profiles(user)],
                         channel='vendor', sender_role='customer', read_by_other=False)
    elif rp is not None:
        qs = base.filter(order__delivery_info__rider=rp, channel='rider', sender_role='customer', read_by_other=False)
    else:
        return JsonResponse({'success': True, 'orders': {}, 'total': 0})
    # Purane khatam orders ke paigham badge mein na ginein
    qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=3))
    orders, total = {}, 0
    for row in qs.values('order_id', 'channel').annotate(n=Count('id')):
        orders.setdefault(str(row['order_id']), {})[row['channel']] = row['n']
        total += row['n']
    resp = JsonResponse({'success': True, 'orders': orders, 'total': total})
    resp['Cache-Control'] = 'no-store'
    return resp
