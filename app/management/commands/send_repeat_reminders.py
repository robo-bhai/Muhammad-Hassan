from django.core.management.base import BaseCommand

from app.customer import repeat_plans


class Command(BaseCommand):
    help = "Repeat orders: jin plans ka waqt aa gaya unhein reminder bhejein (cron se har 5-10 minute mein chalayen)."

    def handle(self, *args, **options):
        sent = repeat_plans.sweep()
        self.stdout.write(self.style.SUCCESS(f"Repeat order reminders sent: {sent}"))
