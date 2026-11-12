"""
WhatsApp automatic updates (order confirm, rider nikla, delivered) - customer aur vendor dono ko.

Kaise kaam karta hai
- Meta WhatsApp Cloud API se khud message jata hai (koi click nahi). Admin Settings > Shop se on/off.
- Credentials secrets/env mein (DB mein nahi):
      WHATSAPP_CLOUD_TOKEN       permanent access token
      WHATSAPP_PHONE_NUMBER_ID   Meta ke "Phone number ID"
      WHATSAPP_API_VERSION       (optional, default v21.0)
- Meta ka qaida: customer ne pichle 24 ghante mein message na kiya ho to sirf approved TEMPLATE jata hai.
  Is liye ek simple template banayen (Utility category), body mein sirf ek variable:
      "{{1}}"           (ya "Online Bazar: {{1}}")
  aur uska naam Settings mein 'WhatsApp template name' mein likhen. Naam khali ho to seedha text jata hai
  (sirf 24 ghante ki window mein pohanchta hai).
- Message bhejna background thread mein hota hai aur kabhi order ko nahi rokta; ghalti sirf log hoti hai.
"""
import logging
import os
import re
import threading

from django.db import transaction

logger = logging.getLogger(__name__)

TIMEOUT = 8

# event -> (customer ko bhejna?, vendor ko bhejna?)
EVENTS = {
    'placed':    (True, True),
    'accept':    (True, False),
    'ready':     (True, False),
    'pickup':    (True, True),
    'delivered': (True, True),
    'reject':    (True, False),
    'expire':    (True, True),
}


# ----------------------------------------------------------------- settings
def _setting_bool(key, default):
    from ..models import SystemSetting
    return SystemSetting.get_bool(key, default)


def _setting_text(key, default=''):
    from ..models import SystemSetting
    return (SystemSetting.get_value(key, default) or default).strip()


def is_enabled():
    return _setting_bool('whatsapp_auto_enabled', False)


def credentials():
    token = os.environ.get('WHATSAPP_CLOUD_TOKEN', '').strip()
    phone_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    version = os.environ.get('WHATSAPP_API_VERSION', 'v21.0').strip() or 'v21.0'
    return token, phone_id, version


# ----------------------------------------------------------------- phone / text
def normalize_phone(phone):
    """Pakistan ke number ko international digits mein (92300...) badlo. Galat ho to None."""
    digits = re.sub(r'\D', '', str(phone or ''))
    if not digits:
        return None
    if digits.startswith('00'):
        digits = digits[2:]
    elif digits.startswith('0'):
        digits = '92' + digits[1:]
    elif not digits.startswith('92') and len(digits) == 10:
        digits = '92' + digits
    return digits if 11 <= len(digits) <= 15 else None


def _lang_code(raw):
    """Settings lowercase kar deti hain (en_us); Meta ko en_US chahiye."""
    raw = (raw or 'en').replace('-', '_')
    if '_' in raw:
        lang, region = raw.split('_', 1)
        return f'{lang.lower()}_{region.upper()}'
    return raw.lower()


def _template_text(text):
    """Template ke variable mein new line / tab / 4 se zyada spaces allowed nahi."""
    return re.sub(r'\s+', ' ', text).strip()[:900]


def customer_text(order, event, shop, rider=None):
    n = order.order_no
    if event == 'placed':
        return f"Shukriya! Aap ka order #{n} {shop} ko mil gaya hai. Qubool hote hi aap ko batayenge."
    if event == 'accept':
        eta = f" Taqreeban {order.prep_minutes} minute mein tayyar hoga." if order.prep_minutes else ''
        return f"{shop} ne aap ka order #{n} qubool kar liya.{eta}"
    if event == 'ready':
        return f"Aap ka order #{n} tayyar hai."
    if event == 'pickup':
        who = f" Rider: {rider.name} ({rider.phone})." if rider is not None else ''
        return f"Aap ka order #{n} raaste mein hai, rider maal le kar nikal chuka hai.{who}"
    if event == 'delivered':
        return f"Aap ka order #{n} deliver ho gaya. {shop} ko chunne ka shukriya!"
    if event in ('reject', 'expire'):
        return f"Maazrat, order #{n} {shop} se qubool nahi ho saka. Wajah: {order.reject_reason or '-'}"
    return ''


def vendor_text(order, event, shop, rider=None):
    n = order.order_no
    if event == 'placed':
        return f"Naya order #{n}. Dashboard mein Accept ya Reject karein."
    if event == 'pickup':
        who = f" ({rider.name})" if rider is not None else ''
        return f"Order #{n} ka rider{who} maal le kar nikal gaya."
    if event == 'delivered':
        return f"Order #{n} customer tak pahunch gaya."
    if event == 'expire':
        return f"Order #{n} aap ke jawab na dene par khud cancel ho gaya."
    return ''


# ----------------------------------------------------------------- send
def send_message(phone, text):
    """Ek message bhejo. Return (ok, detail). Kabhi exception nahi uthata."""
    token, phone_id, version = credentials()
    to = normalize_phone(phone)
    if not token or not phone_id:
        return False, 'WHATSAPP_CLOUD_TOKEN / WHATSAPP_PHONE_NUMBER_ID set nahi'
    if not to:
        return False, 'number galat ya khali'
    template = _setting_text('whatsapp_template_name')
    if template:
        payload = {
            'messaging_product': 'whatsapp', 'to': to, 'type': 'template',
            'template': {
                'name': template,
                'language': {'code': _lang_code(_setting_text('whatsapp_template_lang', 'en'))},
                'components': [{'type': 'body',
                                'parameters': [{'type': 'text', 'text': _template_text(text)}]}],
            },
        }
    else:
        payload = {'messaging_product': 'whatsapp', 'to': to, 'type': 'text',
                   'text': {'body': text[:4000], 'preview_url': False}}
    try:
        import requests
        res = requests.post(f'https://graph.facebook.com/{version}/{phone_id}/messages', json=payload,
                            headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
        if res.status_code >= 400:
            return False, f'HTTP {res.status_code}: {res.text[:300]}'
        return True, 'sent'
    except Exception as exc:
        return False, str(exc)


def _send_many(messages):
    for phone, text in messages:
        ok, detail = send_message(phone, text)
        if ok:
            logger.info('WhatsApp auto sent to %s', normalize_phone(phone))
        else:
            logger.warning('WhatsApp auto FAILED (%s): %s', normalize_phone(phone), detail)


def notify(order, event, rider=None):
    """Order ke event par customer/vendor ko WhatsApp bhejo (background mein, commit ke baad).
    Order ko kabhi na rokey: har ghalti yahin pakri jati hai."""
    try:
        if event not in EVENTS or not is_enabled():
            return
        to_customer, to_vendor = EVENTS[event]
        from . import store_orders
        shop = store_orders.store_name(order.vendor_id)
        out = []

        if to_customer and _setting_bool('whatsapp_auto_customer', True):
            text = customer_text(order, event, shop, rider)
            phone = getattr(order.customer, 'contact_number', None)
            if text and phone:
                out.append((phone, text))

        if to_vendor and _setting_bool('whatsapp_auto_vendor', True):
            prof = store_orders.get_store_profile(order.vendor_id)
            text = vendor_text(order, event, shop, rider)
            phone = getattr(getattr(prof, 'vendor', None), 'contact_number', None) if prof else None
            if text and phone:
                out.append((phone, text))

        if not out:
            return

        def _go():
            threading.Thread(target=_send_many, args=(out,), daemon=True).start()

        try:
            transaction.on_commit(_go)        # transaction nahi ho to foran chalta hai
        except Exception:
            _go()
    except Exception:
        logger.exception('WhatsApp auto notify failed (order=%s event=%s)', getattr(order, 'pk', None), event)
