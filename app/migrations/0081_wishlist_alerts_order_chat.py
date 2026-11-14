from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0080_product_hidden_by_suspend'),
    ]

    operations = [
        migrations.AddField(model_name='wishlistitem', name='notify_stock',
                            field=models.BooleanField(default=True)),
        migrations.AddField(model_name='wishlistitem', name='notify_price',
                            field=models.BooleanField(default=True)),
        migrations.AddField(model_name='wishlistitem', name='last_price',
                            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True,
                                                      help_text='Aakhri dekhi hui qeemat; isse neeche jaye to price drop alert')),
        migrations.AddField(model_name='wishlistitem', name='was_out_of_stock',
                            field=models.BooleanField(default=False,
                                                      help_text='Stock 0 hua tha; wapas aane par Back in stock alert')),
        migrations.AddField(model_name='wishlistitem', name='last_alert_at',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(
            name='OrderChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channel', models.CharField(choices=[('vendor', 'Customer <-> Vendor'), ('rider', 'Customer <-> Rider')], max_length=10)),
                ('sender_role', models.CharField(choices=[('customer', 'Customer'), ('vendor', 'Vendor'), ('rider', 'Rider')], max_length=10)),
                ('message', models.CharField(max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_by_customer', models.BooleanField(default=False)),
                ('read_by_other', models.BooleanField(default=False)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_messages', to='app.saleorder')),
                ('sender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_chat_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Order Chat Message', 'verbose_name_plural': 'Order Chat Messages', 'ordering': ['id']},
        ),
        migrations.AddIndex(model_name='orderchatmessage',
                            index=models.Index(fields=['order', 'channel', 'id'], name='app_ordchat_ord_chan_idx')),
    ]
