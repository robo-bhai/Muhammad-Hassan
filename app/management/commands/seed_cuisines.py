from django.core.management.base import BaseCommand

from app.models import Cuisine

DEFAULTS = [
    ('Pizza', '🍕'), ('Burger', '🍔'), ('Biryani', '🍛'), ('BBQ', '🍢'), ('Chinese', '🥡'),
    ('Fast Food', '🍟'), ('Desserts', '🍰'), ('Coffee', '☕'), ('Shawarma', '🌯'), ('Arabic', '🥙'),
    ('Seafood', '🦐'), ('Healthy', '🥗'),
]


class Command(BaseCommand):
    help = "Common cuisines add karta hai (jo pehle se hon unhe nahi chhoota)."

    def handle(self, *args, **opts):
        made = 0
        for i, (name, icon) in enumerate(DEFAULTS):
            _, created = Cuisine.objects.get_or_create(name=name, defaults={'icon': icon, 'sort_order': i})
            made += created
        self.stdout.write(self.style.SUCCESS(f'{made} cuisine(s) add hui.'))
