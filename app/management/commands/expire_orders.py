"""
Vendor ne waqt par Accept/Reject nahi kiya to store order khud cancel (Talabat jaisa).
Timeout: settings.VENDOR_ACCEPT_TIMEOUT_MINUTES (default 5, 0 = band).

Usage:
    python manage.py expire_orders                 # ek baar chalao (cron har minute)
    python manage.py expire_orders --loop 30       # har 30 second mein chalta rahe
"""
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Jawab na dene wale store orders cancel karo'

    def add_arguments(self, parser):
        parser.add_argument('--loop', type=int, default=0,
                            help='Itne second baad dobara chalao (0 = sirf ek baar)')

    def handle(self, *args, **options):
        from app.customer import store_orders

        if not store_orders.accept_timeout_minutes():
            self.stdout.write('VENDOR_ACCEPT_TIMEOUT_MINUTES = 0, auto-expire band hai.')
            return
        loop = max(options['loop'], 0)
        while True:
            count = store_orders.expire_unaccepted_orders()
            if count or not loop:
                self.stdout.write(f'{count} order expire hue.')
            if not loop:
                break
            time.sleep(loop)
