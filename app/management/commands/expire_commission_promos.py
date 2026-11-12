"""
Launch/promo commission ki date guzar chuki ho to vendor ko normal commission par wapas lao.
Commission batch ke cost me bake hoti hai, is liye open batches dobara reprice hote hain.

Usage:
    python manage.py expire_commission_promos        # roz ek dafa (raat ko, cron)
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Promo commission ki date guzar chuki vendors ko normal rate par wapas lao'

    def handle(self, *args, **options):
        from app.customer.vendor_commission import expire_promos
        count = expire_promos()
        self.stdout.write(self.style.SUCCESS(f'{count} vendor(s) normal commission par wapas aa gaye.'))
