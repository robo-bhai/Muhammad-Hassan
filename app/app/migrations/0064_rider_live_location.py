from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0063_orderdispute_responses'),
    ]

    operations = [
        migrations.AddField(model_name='riderprofile', name='last_lat',
                            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
        migrations.AddField(model_name='riderprofile', name='last_lng',
                            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
        migrations.AddField(model_name='riderprofile', name='last_location_at',
                            field=models.DateTimeField(blank=True, null=True)),
    ]
