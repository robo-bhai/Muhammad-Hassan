from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0051_deliveryarea'),
    ]

    operations = [
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Customer yeh code likhta hai (jaise WELCOME20). Capital mein save hota hai', max_length=30, unique=True)),
                ('title', models.CharField(blank=True, default='', help_text="Store card par badge: jaise '20% off' ya 'Rs 100 off'. Khali = khud ban jata hai", max_length=80)),
                ('discount_type', models.CharField(choices=[('percent', 'Percent (%)'), ('fixed', 'Fixed amount')], default='percent', max_length=7)),
                ('value', models.DecimalField(decimal_places=2, help_text='Percent ho to 1-100, fixed ho to raqam', max_digits=10)),
                ('max_discount', models.DecimalField(blank=True, decimal_places=2, help_text='Percent coupon ki hadd (khali = koi hadd nahi)', max_digits=10, null=True)),
                ('min_order', models.DecimalField(decimal_places=2, default=0, help_text='Kam az kam order (items ka subtotal)', max_digits=10)),
                ('show_on_store', models.BooleanField(default=True, help_text='ON = store card/page par offer badge dikhao (sirf store wale coupon ka)')),
                ('first_order_only', models.BooleanField(default=False, help_text='Sirf customer ke pehle order par')),
                ('usage_limit', models.PositiveIntegerField(blank=True, help_text='Kul kitni dafa use ho sakta hai (khali = bepanah)', null=True)),
                ('per_customer_limit', models.PositiveIntegerField(default=1, help_text='Ek customer kitni dafa (0 = bepanah)')),
                ('starts_on', models.DateField(blank=True, null=True)),
                ('ends_on', models.DateField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(blank=True, help_text='Khali = har store par chalega. Store chunein to sirf us store par', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='coupons', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Coupon',
                'verbose_name_plural': 'Coupons',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CouponRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('coupon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='redemptions', to='app.coupon')),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coupon_redemptions', to='app.customer')),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='coupon_redemption', to='app.saleorder')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
