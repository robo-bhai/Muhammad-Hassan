from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0082_repeat_order_plans'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wallettransaction', name='kind',
            field=models.CharField(choices=[('topup', 'Top-up (admin ne jama kiya)'), ('adjust', 'Adjustment (admin)'), ('spend', 'Order mein kharch'), ('refund', 'Order cancel - wapas'), ('cashback', 'Cashback reward'), ('points', 'Loyalty points se credit'), ('pro', 'Pro membership ki payment'), ('dispute', 'Dispute refund'), ('referral', 'Referral reward (dost laaya)'), ('refbonus', 'Referral welcome bonus'), ('giftcard', 'Gift card redeem')], max_length=10),
        ),
        migrations.CreateModel(
            name='GiftCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(choices=[('active', 'Active'), ('redeemed', 'Redeemed'), ('cancelled', 'Cancelled')], db_index=True, default='active', max_length=10)),
                ('expires_at', models.DateTimeField(blank=True, help_text='Khali = kabhi expire nahi', null=True)),
                ('recipient_name', models.CharField(blank=True, max_length=100)),
                ('message', models.CharField(blank=True, max_length=200)),
                ('redeemed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('buyer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gift_cards_bought', to='app.customer')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('redeemed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gift_cards_redeemed', to='app.customer')),
            ],
            options={'verbose_name': 'Gift Card', 'verbose_name_plural': 'Gift Cards', 'ordering': ['-created_at', '-id']},
        ),
        migrations.CreateModel(
            name='WalletTopUp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('topup', 'Wallet top-up'), ('gift', 'Gift card purchase')], default='topup', max_length=5)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('method', models.CharField(choices=[('jazzcash', 'JazzCash'), ('easypaisa', 'EasyPaisa'), ('bank', 'Bank transfer'), ('cash', 'Cash')], default='jazzcash', max_length=10)),
                ('reference', models.CharField(blank=True, help_text='Transaction ID / reference', max_length=80)),
                ('recipient_name', models.CharField(blank=True, max_length=100)),
                ('message', models.CharField(blank=True, max_length=200)),
                ('status', models.CharField(choices=[('pending', 'Pending (payment check hona baqi)'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=10)),
                ('admin_note', models.CharField(blank=True, max_length=200)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wallet_topups', to='app.customer')),
                ('gift_card', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.giftcard')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Wallet Top-up Request', 'verbose_name_plural': 'Wallet Top-up Requests', 'ordering': ['-created_at', '-id']},
        ),
        migrations.AddIndex(model_name='wallettopup',
                            index=models.Index(fields=['status', 'created_at'], name='app_topup_status_idx')),
    ]
