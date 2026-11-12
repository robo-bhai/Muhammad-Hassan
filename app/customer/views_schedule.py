"""Checkout par "baad ke liye schedule": waqt session mein rakhta hai (order banate waqt dobara jaancha jata hai)."""
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
import json

from . import store_orders


@require_POST
def set_schedule(request):
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        data = {}
    raw = (data.get('scheduled_for') or '').strip()

    if not raw:                       # "Jaldi se jaldi"
        request.session.pop(store_orders.SCHEDULE_SESSION_KEY, None)
        request.session.modified = True
        return JsonResponse({'success': True, 'scheduled_for': ''})

    try:
        when = store_orders.parse_schedule(raw)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid time hai.'})

    cart = request.session.get('cart', {})
    err = store_orders.schedule_error(cart, when) if cart else 'Cart khali hai.'
    if err:
        return JsonResponse({'success': False, 'message': err})

    request.session[store_orders.SCHEDULE_SESSION_KEY] = timezone.localtime(when).strftime('%Y-%m-%dT%H:%M')
    request.session.modified = True
    return JsonResponse({
        'success': True,
        'scheduled_for': request.session[store_orders.SCHEDULE_SESSION_KEY],
        'label': timezone.localtime(when).strftime('%d %b, %I:%M %p'),
    })
