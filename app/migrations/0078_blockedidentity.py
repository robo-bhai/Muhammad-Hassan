import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0077_customerprofile_suspend'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BlockedIdentity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('phone', 'Phone'), ('email', 'Email'), ('device', 'Device (IP + browser)')], db_index=True, max_length=10)),
                ('value', models.CharField(db_index=True, max_length=128)),
                ('label', models.CharField(blank=True, default='', help_text='Dikhane ke liye (asli phone/email)', max_length=120)),
                ('reason', models.CharField(blank=True, default='', max_length=255)),
                ('source', models.CharField(blank=True, default='manual', max_length=12)),
                ('source_ref', models.CharField(blank=True, db_index=True, default='', max_length=40)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Blocked identity',
                'verbose_name_plural': 'Blocked identities',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='blockedidentity',
            constraint=models.UniqueConstraint(fields=('kind', 'value'), name='uniq_blocked_kind_value'),
        ),
        migrations.AddField(
            model_name='customerprofile',
            name='signup_device',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='signup_device',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
