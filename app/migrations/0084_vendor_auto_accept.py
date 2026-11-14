from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0083_wallet_funds'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile', name='auto_accept',
            field=models.BooleanField(default=False, help_text='ON = naya order aate hi khud qubool ho jata hai (ringtone nahi bajti). Customer ko ETA mil jati hai.', verbose_name='Auto-accept orders'),
        ),
        migrations.AddField(
            model_name='vendorprofile', name='auto_accept_prep_minutes',
            field=models.PositiveSmallIntegerField(default=20, help_text='Auto-accept par customer ko itne minute mein tayyar hone ka ETA dikhta hai.', verbose_name='Auto-accept prep time (min)'),
        ),
    ]
