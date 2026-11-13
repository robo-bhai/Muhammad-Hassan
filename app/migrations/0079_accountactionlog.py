import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_current_suspensions(apps, schema_editor):
    """Jo customers abhi suspend hain unki history ek entry se shuru karo (vendors ka suspend record pehle nahi tha)."""
    CustomerProfile = apps.get_model('app', 'CustomerProfile')
    AccountActionLog = apps.get_model('app', 'AccountActionLog')
    for p in CustomerProfile.objects.filter(is_suspended=True).select_related('customer', 'suspended_by'):
        log = AccountActionLog.objects.create(
            kind='customer', ref_id=p.customer_id, name=(p.customer.name or '')[:150], action='suspend',
            reason=p.suspended_reason or '', detail='Pehle se suspend tha (history se pehle)',
            by=p.suspended_by, by_name=(p.suspended_by.username if p.suspended_by else '')[:150])
        if p.suspended_at:
            AccountActionLog.objects.filter(pk=log.pk).update(created_at=p.suspended_at)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0078_blockedidentity'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('customer', 'Customer'), ('vendor', 'Vendor'), ('other', 'Other')], db_index=True, max_length=10)),
                ('ref_id', models.PositiveIntegerField(blank=True, help_text='Customer ya Vendor ka id', null=True)),
                ('name', models.CharField(blank=True, default='', max_length=150)),
                ('action', models.CharField(choices=[('suspend', 'Suspend'), ('unsuspend', 'Unsuspend'), ('approve', 'Approve'), ('block', 'Blacklist add'), ('unblock', 'Blacklist remove')], db_index=True, max_length=10)),
                ('reason', models.CharField(blank=True, default='', max_length=255)),
                ('detail', models.CharField(blank=True, default='', max_length=255)),
                ('by_name', models.CharField(blank=True, default='', max_length=150)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Account action log',
                'verbose_name_plural': 'Account action logs',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.RunPython(backfill_current_suspensions, migrations.RunPython.noop),
    ]
