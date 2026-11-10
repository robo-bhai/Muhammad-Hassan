from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0053_product_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleorderitem',
            name='options_text',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='saleorderitem',
            name='options_key',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='saleorderitem',
            name='options_extra',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Options ki extra raqam (per unit), price mein shamil', max_digits=10),
        ),
        migrations.AlterUniqueTogether(
            name='saleorderitem',
            unique_together={('order', 'product', 'options_key')},
        ),
        migrations.AddField(
            model_name='saleitem',
            name='options_text',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='options_extra_share',
            field=models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=10),
        ),
    ]
