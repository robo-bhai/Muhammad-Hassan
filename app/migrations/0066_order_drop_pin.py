from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0065_auto_dispatch'),
    ]

    operations = [
        migrations.AddField(model_name='saleorder', name='delivery_lat',
                            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
        migrations.AddField(model_name='saleorder', name='delivery_lng',
                            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
    ]
