from django.db import migrations

SAFE_TEXT = 'Details removed for security. Open OTP management to see the request.'


def scrub(apps, schema_editor):
    """Purani 'New OTP' notifications mein phone, email, token aur verify link the - hata do."""
    Notification = apps.get_model('app', 'Notification')
    Notification.objects.filter(title__startswith='🔐 New OTP').update(message=SAFE_TEXT)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0092_vendor_documents'),
    ]

    operations = [
        migrations.RunPython(scrub, migrations.RunPython.noop),
    ]
