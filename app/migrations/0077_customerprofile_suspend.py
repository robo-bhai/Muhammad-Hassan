import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0076_store_deals'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='customerprofile',
            name='is_suspended',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Suspended'),
        ),
        migrations.AddField(
            model_name='customerprofile',
            name='suspended_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='customerprofile',
            name='suspended_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='customerprofile',
            name='suspended_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Suspended by'),
        ),
    ]
