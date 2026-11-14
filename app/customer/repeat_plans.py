"""
Repeat orders (daily / weekly): customer pichle order ko schedule par dohrata hai.

Design: order apne aap place NAHI hota (OTP, address, payment customer ke haath mein rehte hain).
Waqt aane par customer ko notification + push milta hai; ek tap par purane order ka maal cart mein
aa jata hai (views_reorder wali wahi jaanch: stock, band store, naye daam) aur wo confirm karta hai.
"""
import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_PLANS_PER_CUSTOMER = 10
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def next_occurrence(after, frequency, weekday, at):
    """Pure: `after` (naive local datetime) ke baad ka pehla waqt. daily = har roz `at`; weekly = `weekday` (0=Mon) ko `at`."""
    cand = datetime.combine(after.date(), at)
    if frequency == 'weekly':
        cand += timedelta(days=(weekday - cand.weekday()) % 7)
    while cand <= after:
        cand += timedelta(days=7 if frequency == 'weekly' else 1)
    return cand


def compute_next_run(frequency, weekday, at, after=None):
    """Aware datetime (project ke timezone mein)."""
    after = timezone.localtime(after or timezone.now()).replace(tzinfo=None)
    naive = next_occurrence(after, frequency, weekday, at)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def parse_time(raw):
    """'07:30' -> time; galat ho to ValueError."""
    return datetime.strptime((raw or '').strip(), '%H:%M').time()


def describe(plan):
    when = plan.time_of_day.strftime('%I:%M %p').lstrip('0')
    if plan.frequency == 'weekly':
        return f'Every {WEEKDAYS[plan.weekday % 7]} at {when}'
    return f'Every day at {when}'


def _customer_user(customer):
    portal = getattr(customer, 'portal_profile', None)
    return getattr(portal, 'user', None)


def sweep(now=None):
    """Jin plans ka waqt aa gaya unhein yaad dihani bhejo (cron se har 5-10 minute). Wapas: bheje gaye reminders."""
    from ..models import RepeatOrderPlan
    from .store_orders import _notify
    now = now or timezone.now()
    sent = 0
    due = (RepeatOrderPlan.objects.filter(is_active=True, next_run_at__lte=now)
           .select_related('customer', 'source_order')[:500])
    for plan in due:
        try:
            # Agle waqt par aage barho (chhute hue waqt ke reminders ka dher nahi lagta)
            plan.next_run_at = compute_next_run(plan.frequency, plan.weekday, plan.time_of_day, after=now)
            if plan.source_order_id is None:
                plan.is_active = False          # asal order nahi raha
                plan.save(update_fields=['is_active', 'next_run_at'])
                continue
            plan.last_notified_at = now
            plan.save(update_fields=['next_run_at', 'last_notified_at'])
            user = _customer_user(plan.customer)
            if user:
                label = plan.store_name or 'your store'
                _notify(user, 'Time to reorder?',
                        f'{label}: {plan.summary or "your usual order"} - tap to add it to your cart.',
                        link=f'/shop/repeat/?due={plan.pk}', kind='info')
                sent += 1
        except Exception:
            logger.exception('Repeat plan %s reminder failed', plan.pk)
    return sent
