from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0084_vendor_auto_accept'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile', name='hide_sold_out',
            field=models.BooleanField(default=False, help_text='ON = stock 0 hote hi maal customer ko dikhna band (store page / shop home); restock par khud wapas aa jata hai.', verbose_name='Hide sold-out products'),
        ),
        migrations.AddField(
            model_name='vendorprofile', name='low_stock_level',
            field=models.PositiveSmallIntegerField(blank=True, help_text="Is store ke maal par itne ya kam bachne par 'Low stock' alert. Khali = shop ki default hadd.", null=True, verbose_name='Low-stock alert level'),
        ),
    ]
