"""
Purane (plaintext) address / CNIC data ko encrypt karta hai.

    python manage.py encrypt_existing_data --dry-run     # sirf ginti dikhaye
    python manage.py encrypt_existing_data               # asal mein encrypt

Pehle DATA_ENCRYPTION_KEY set karein aur DATABASE KA BACKUP lein. Command dobara chalane par koi nuqsan nahi:
jo rows pehle se encrypted hain (prefix 'enc1:') unhein chhoota nahi.
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection

from app.security.field_crypto import PREFIX

TARGETS = [
    ('CustomerAddress', ['address_line_1', 'address_line_2', 'landmark']),
    ('CustomerOrder', ['shipping_address', 'shipping_landmark', 'billing_address']),
    ('DeliveryInfo', ['rider_cnic']),
    ('Customer', ['address']),
]


class Command(BaseCommand):
    help = 'Purane plaintext address/CNIC rows ko encrypt karta hai.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Kuch badle baghair ginti dikhao')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        qn = connection.ops.quote_name
        grand = 0
        for model_name, fields in TARGETS:
            Model = apps.get_model('app', model_name)
            table = qn(Model._meta.db_table)
            pk_col = qn(Model._meta.pk.column)
            for fname in fields:
                col = qn(Model._meta.get_field(fname).column)
                with connection.cursor() as cur:
                    cur.execute(
                        'SELECT %s, %s FROM %s WHERE %s IS NOT NULL AND %s <> %%s AND %s NOT LIKE %%s'
                        % (pk_col, col, table, col, col, col), ['', PREFIX + '%'])
                    rows = cur.fetchall()
                if not dry:
                    for pk, plain in rows:
                        # ORM update() get_prep_value se guzarta hai, yani yahan value encrypt ho kar save hoti hai
                        Model.objects.filter(pk=pk).update(**{fname: plain})
                self.stdout.write('%s.%s: %d rows %s' % (model_name, fname, len(rows),
                                                          'milay' if dry else 'encrypt kiye'))
                grand += len(rows)
        self.stdout.write(self.style.SUCCESS('Total: %d%s' % (grand, ' (dry-run)' if dry else '')))
