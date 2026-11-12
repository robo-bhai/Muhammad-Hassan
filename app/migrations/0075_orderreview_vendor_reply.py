from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0074_store_sponsorship'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderreview',
            name='vendor_reply',
            field=models.CharField(blank=True, default='', help_text='Store ka public jawab (customer aur store page par dikhta hai)', max_length=300),
        ),
        migrations.AddField(
            model_name='orderreview',
            name='vendor_replied_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
