import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0075_orderreview_vendor_reply'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreDeal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('bogo', 'Buy 1 Get 1 Free'), ('combo', 'Combo deal'), ('flash', 'Flash sale')], max_length=10)),
                ('title', models.CharField(max_length=80)),
                ('percent', models.DecimalField(blank=True, decimal_places=2, help_text='Flash sale: kitne percent discount', max_digits=5, null=True)),
                ('combo_price', models.DecimalField(blank=True, decimal_places=2, help_text='Combo: poore set ki qeemat', max_digits=10, null=True)),
                ('starts_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('ends_at', models.DateTimeField(blank=True, help_text='Khali = jab tak vendor khud band na kare', null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deals', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Store Deal',
                'verbose_name_plural': 'Store Deals',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='StoreDealItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qty', models.PositiveSmallIntegerField(default=1)),
                ('deal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='app.storedeal')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deal_items', to='app.product')),
            ],
            options={
                'verbose_name': 'Store Deal Item',
                'verbose_name_plural': 'Store Deal Items',
            },
        ),
        migrations.CreateModel(
            name='OrderDeal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=80)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('deal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uses', to='app.storedeal')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deals_applied', to='app.saleorder')),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deal_discounts', to='app.vendor')),
            ],
            options={
                'verbose_name': 'Order Deal',
                'verbose_name_plural': 'Order Deals',
            },
        ),
    ]
