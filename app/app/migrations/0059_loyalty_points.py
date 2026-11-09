from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0058_offers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wallettransaction',
            name='kind',
            field=models.CharField(choices=[('topup', 'Top-up (admin ne jama kiya)'), ('adjust', 'Adjustment (admin)'), ('spend', 'Order mein kharch'), ('refund', 'Order cancel - wapas'), ('cashback', 'Cashback reward'), ('points', 'Loyalty points se credit'), ('pro', 'Pro membership ki payment')], max_length=10),
        ),
        migrations.CreateModel(
            name='LoyaltyTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('points', models.IntegerField(help_text='+ mile, - kharch')),
                ('kind', models.CharField(choices=[('earn', 'Order par points mile'), ('redeem', 'Wallet credit mein badle'), ('adjust', 'Adjustment (admin)')], max_length=8)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_transactions', to='app.customer')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='loyalty_transactions', to='app.saleorder')),
            ],
            options={
                'verbose_name': 'Loyalty Points Entry',
                'verbose_name_plural': 'Loyalty Points',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='loyaltytransaction',
            index=models.Index(fields=['customer', 'created_at'], name='loyalty_cust_created_idx'),
        ),
        migrations.AddConstraint(
            model_name='loyaltytransaction',
            constraint=models.UniqueConstraint(condition=models.Q(('order__isnull', False)), fields=('order', 'kind'), name='loyalty_one_per_order_kind'),
        ),
    ]
