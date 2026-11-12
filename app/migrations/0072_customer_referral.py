import secrets

import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def fill_codes(apps, schema_editor):
    """Purane customers ko bhi referral code do (naye profile ko model.save khud deta hai)."""
    Profile = apps.get_model('app', 'CustomerProfile')
    used = set(Profile.objects.exclude(referral_code__isnull=True).values_list('referral_code', flat=True))
    for pk in Profile.objects.filter(referral_code__isnull=True).values_list('pk', flat=True):
        while True:
            code = ''.join(secrets.choice(ALPHABET) for _ in range(8))
            if code not in used:
                used.add(code)
                break
        Profile.objects.filter(pk=pk).update(referral_code=code)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0071_vendor_commission_promo'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerprofile',
            name='referral_code',
            field=models.CharField(blank=True, editable=False, max_length=8, null=True, unique=True,
                                   verbose_name='Referral Code'),
        ),
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='wallettransaction',
            name='kind',
            field=models.CharField(choices=[
                ('topup', 'Top-up (admin ne jama kiya)'),
                ('adjust', 'Adjustment (admin)'),
                ('spend', 'Order mein kharch'),
                ('refund', 'Order cancel - wapas'),
                ('cashback', 'Cashback reward'),
                ('points', 'Loyalty points se credit'),
                ('pro', 'Pro membership ki payment'),
                ('dispute', 'Dispute refund'),
                ('referral', 'Referral reward (dost laaya)'),
                ('refbonus', 'Referral welcome bonus'),
            ], max_length=10),
        ),
        migrations.CreateModel(
            name='Referral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending (pehle order ka intezar)'),
                    ('rewarded', 'Rewarded'),
                    ('rejected', 'Rejected'),
                ], default='pending', max_length=10)),
                ('reject_reason', models.CharField(blank=True, default='', max_length=120)),
                ('device_hash', models.CharField(
                    blank=True, db_index=True, default='', max_length=64,
                    help_text='Register ke waqt IP + browser ka hash (asal IP save nahi hota)')),
                ('referrer_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('referee_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rewarded_at', models.DateTimeField(blank=True, null=True)),
                ('referee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                 related_name='referral_received', to='app.customer')),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='referrals_made', to='app.customer')),
                ('reward_order', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to='app.saleorder', help_text='Jis order par reward mila')),
            ],
            options={
                'verbose_name': 'Referral',
                'verbose_name_plural': 'Referrals',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='referral',
            index=models.Index(fields=['referrer', 'status', 'rewarded_at'], name='referral_ref_status_idx'),
        ),
    ]
