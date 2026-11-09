from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0054_order_item_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_popular',
            field=models.BooleanField(default=False, help_text='Store page ke Popular section mein dikhao', verbose_name='Popular'),
        ),
        migrations.AddField(
            model_name='saleorderitem',
            name='note',
            field=models.CharField(blank=True, default='', help_text='Customer ki special instruction (jaise: pyaaz na daalein)', max_length=200),
        ),
        migrations.AddField(
            model_name='productoptiongroup',
            name='parent_option',
            field=models.ForeignKey(blank=True, help_text='Khali = hamesha dikhao. Option chunein to ye group sirf tab dikhega jab wo option chuna ho', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='child_groups', to='app.productoption'),
        ),
        migrations.CreateModel(
            name='StoreMenuSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Chhota number pehle nazar aata hai')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='app.category')),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='menu_sections', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Store Menu Section',
                'verbose_name_plural': 'Store Menu Sections',
                'ordering': ['sort_order', 'id'],
                'unique_together': {('store', 'category')},
            },
        ),
    ]
