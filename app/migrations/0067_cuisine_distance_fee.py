from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0066_order_drop_pin'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cuisine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, unique=True)),
                ('icon', models.CharField(blank=True, default='🍽️', help_text='Ek emoji, jaise 🍕 🍔 🍛', max_length=8)),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Chhota number pehle nazar aata hai')),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'verbose_name': 'Cuisine', 'verbose_name_plural': '3.1b Cuisines', 'ordering': ['sort_order', 'name']},
        ),
        migrations.AddField(
            model_name='deliveryarea', name='extra_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8,
                help_text='Is area mein deliver karne par store ki fee ke upar extra (door ke areas ke liye). 0 = koi extra nahi.'),
        ),
        migrations.AddField(
            model_name='vendorprofile', name='fee_per_km',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name='Fee per km',
                help_text='Free distance ke baad har extra km par itni fee. 0 = distance fee band (sirf upar wali fixed fee).'),
        ),
        migrations.AddField(
            model_name='vendorprofile', name='free_radius_km',
            field=models.DecimalField(decimal_places=1, default=0, max_digits=5, verbose_name='Free radius (km)',
                help_text='Itne km tak sirf base delivery fee lagti hai.'),
        ),
        migrations.AddField(
            model_name='vendorprofile', name='max_delivery_km',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name='Max delivery distance (km)',
                help_text='Is se door customer ko deliver nahi hota. Khali = koi had nahi.'),
        ),
        migrations.AddField(
            model_name='vendorprofile', name='cuisines',
            field=models.ManyToManyField(blank=True, related_name='stores', to='app.cuisine',
                help_text='Is store ka khana (zyada se zyada 3). Customer stores page par cuisine se filter karta hai.'),
        ),
    ]
