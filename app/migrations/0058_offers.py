from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0057_vendor_busy_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleorder',
            name='wallet_paid',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12),
        ),
        migrations.AddField(
            model_name='saleorder',
            name='pro_delivery_waived',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.CreateModel(
            name='WalletTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, help_text='+ jama, - kharch', max_digits=12)),
                ('kind', models.CharField(choices=[('topup', 'Top-up (admin ne jama kiya)'), ('adjust', 'Adjustment (admin)'), ('spend', 'Order mein kharch'), ('refund', 'Order cancel - wapas'), ('cashback', 'Cashback reward')], max_length=10)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wallet_transactions', to='app.customer')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='wallet_transactions', to='app.saleorder')),
            ],
            options={
                'verbose_name': 'Wallet Transaction',
                'verbose_name_plural': 'Wallet Transactions',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='wallettransaction',
            index=models.Index(fields=['customer', 'created_at'], name='wallet_cust_created_idx'),
        ),
        migrations.AddConstraint(
            model_name='wallettransaction',
            constraint=models.UniqueConstraint(condition=models.Q(('order__isnull', False)), fields=('order', 'kind'), name='wallet_one_per_order_kind'),
        ),
        migrations.CreateModel(
            name='ProMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending (payment ka intezar)'), ('active', 'Active'), ('cancelled', 'Cancelled')], default='pending', max_length=10)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('starts_on', models.DateField(blank=True, null=True)),
                ('ends_on', models.DateField(blank=True, null=True)),
                ('amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Customer se li gayi raqam (record ke liye)', max_digits=10)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pro_memberships', to='app.customer')),
            ],
            options={
                'verbose_name': 'Pro Membership',
                'verbose_name_plural': 'Pro Memberships',
                'ordering': ['-requested_at'],
            },
        ),
    ]
