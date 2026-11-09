import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0049_encrypt_sensitive_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorPayout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('method', models.CharField(choices=[('cash', 'Cash'), ('bank', 'Bank Transfer'), ('jazzcash', 'JazzCash'), ('easypaisa', 'EasyPaisa'), ('cheque', 'Cheque')], default='bank', max_length=12)),
                ('reference_no', models.CharField(blank=True, default='', help_text='Transaction ID / cheque number', max_length=100)),
                ('notes', models.TextField(blank=True, default='')),
                ('paid_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marketplace_payouts', to='app.vendor')),
            ],
            options={
                'verbose_name': 'Vendor Payout',
                'verbose_name_plural': '3.4 Vendor Payouts',
                'ordering': ['-paid_at', '-id'],
                'indexes': [models.Index(fields=['vendor', 'paid_at'], name='app_vendorp_vendor_idx')],
            },
        ),
    ]
