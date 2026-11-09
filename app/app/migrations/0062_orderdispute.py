from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0061_pushsubscription'),
    ]

    operations = [
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
            ], max_length=10),
        ),
        migrations.CreateModel(
            name='OrderDispute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[
                    ('missing_item', 'Item missing'), ('wrong_item', 'Wrong item'),
                    ('bad_quality', 'Bad quality / damaged'), ('late', 'Very late delivery'),
                    ('not_received', 'Order not received'), ('extra_charge', 'Extra charge'),
                    ('rider_behavior', 'Rider behaviour'), ('other', 'Other')], max_length=20)),
                ('description', models.TextField(blank=True, default='')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='disputes/%Y/%m/')),
                ('status', models.CharField(choices=[
                    ('open', 'Open'), ('under_review', 'Under review'),
                    ('resolved', 'Resolved'), ('rejected', 'Rejected')],
                    db_index=True, default='open', max_length=15)),
                ('resolution', models.CharField(blank=True, choices=[
                    ('refund_full', 'Full refund to wallet'),
                    ('refund_partial', 'Partial refund to wallet'),
                    ('no_refund', 'No refund')], default='', max_length=15)),
                ('refund_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('admin_note', models.CharField(blank=True, default='', help_text='Customer ko dikhne wala jawab', max_length=300)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='disputes', to='app.customer')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('rider', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='disputes', to='app.riderprofile')),
                ('sale_order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dispute', to='app.saleorder')),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='disputes', to='app.vendor')),
            ],
            options={
                'verbose_name': 'Order Dispute',
                'verbose_name_plural': 'Order Disputes',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='orderdispute',
            index=models.Index(fields=['status', 'created_at'], name='dispute_status_created_idx'),
        ),
    ]
