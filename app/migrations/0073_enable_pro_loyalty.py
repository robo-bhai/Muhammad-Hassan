from django.db import migrations

FLAGS = ('shop_pro_enabled', 'shop_loyalty_enabled')


def enable(apps, schema_editor):
    """Pro membership aur Loyalty points ko ON karo (admin baad mein Settings > Shop se band kar sakta hai)."""
    Setting = apps.get_model('app', 'SystemSetting')
    for key in FLAGS:
        Setting.objects.update_or_create(setting_key=key, defaults={'setting_value': 'true'})


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0072_customer_referral'),
    ]

    operations = [
        migrations.RunPython(enable, migrations.RunPython.noop),
    ]
