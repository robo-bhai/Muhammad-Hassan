from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0068_otp_reset_purposes'),
    ]

    operations = [
        migrations.RemoveField(model_name='translation', name='ar'),
        migrations.RemoveField(model_name='translation', name='ar_status'),
    ]
