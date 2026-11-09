from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0062_orderdispute'),
    ]

    operations = [
        migrations.AddField(model_name='orderdispute', name='vendor_response',
                            field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='orderdispute', name='vendor_photo',
                            field=models.ImageField(blank=True, null=True, upload_to='disputes/%Y/%m/')),
        migrations.AddField(model_name='orderdispute', name='vendor_responded_at',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='orderdispute', name='rider_response',
                            field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='orderdispute', name='rider_photo',
                            field=models.ImageField(blank=True, null=True, upload_to='disputes/%Y/%m/')),
        migrations.AddField(model_name='orderdispute', name='rider_responded_at',
                            field=models.DateTimeField(blank=True, null=True)),
    ]
