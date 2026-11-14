from django.core.management.base import BaseCommand

from app.customer import wishlist_alerts


class Command(BaseCommand):
    help = "Wishlist alerts: Back in stock aur Price drop (cron se har 10-15 minute mein chalayen)."

    def handle(self, *args, **options):
        stock, price = wishlist_alerts.sweep()
        self.stdout.write(self.style.SUCCESS(f"Back in stock alerts: {stock}, price drop alerts: {price}"))
