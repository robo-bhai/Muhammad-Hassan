import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0069_remove_translation_arabic'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='payout_method',
            field=models.CharField(
                blank=True, default='', max_length=12,
                choices=[('bank', 'Bank Transfer'), ('jazzcash', 'JazzCash'), ('easypaisa', 'EasyPaisa')]),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='payout_account_title',
            field=models.CharField(blank=True, default='', help_text='Account holder ka naam', max_length=100),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='payout_account_no',
            field=models.CharField(blank=True, default='',
                                   help_text='IBAN / account number / mobile account number', max_length=50),
        ),
        migrations.CreateModel(
            name='VendorPayoutRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('method', models.CharField(
                    default='bank', max_length=12,
                    choices=[('bank', 'Bank Transfer'), ('jazzcash', 'JazzCash'), ('easypaisa', 'EasyPaisa')])),
                ('account_title', models.CharField(blank=True, default='', max_length=100)),
                ('account_no', models.CharField(blank=True, default='', max_length=50)),
                ('note', models.CharField(blank=True, default='', help_text='Vendor ka paigham', max_length=200)),
                ('status', models.CharField(
                    db_index=True, default='pending', max_length=10,
                    choices=[('pending', 'Pending'), ('paid', 'Paid'), ('rejected', 'Rejected'),
                             ('cancelled', 'Cancelled by vendor')])),
                ('reject_reason', models.CharField(blank=True, default='', max_length=200)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('payout', models.OneToOneField(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='request', to='app.vendorpayout')),
                ('reviewed_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name='payout_requests',
                    to='app.vendor')),
            ],
            options={
                'verbose_name': 'Vendor Payout Request',
                'verbose_name_plural': '3.5 Vendor Payout Requests',
                'ordering': ['-requested_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='vendorpayoutrequest',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'pending')), fields=('vendor',),
                name='one_pending_payout_request_per_vendor'),
        ),
    ]
