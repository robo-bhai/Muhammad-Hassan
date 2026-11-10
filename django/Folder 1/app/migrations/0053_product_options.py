from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0052_coupon'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductOptionGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Jaise: Size, Flavour, Extras', max_length=60)),
                ('kind', models.CharField(choices=[('single', 'Ek chunein (jaise Size)'), ('multiple', 'Kai chunein (jaise Extras)')], default='single', max_length=8)),
                ('is_required', models.BooleanField(default=False, help_text='ON = customer ko chunna lazmi hai (jaise Size)')),
                ('max_select', models.PositiveSmallIntegerField(default=0, help_text="'Kai chunein' mein ziyada se ziyada kitne (0 = koi hadd nahi)")),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Chhota number pehle nazar aata hai')),
                ('is_active', models.BooleanField(default=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='option_groups', to='app.product')),
            ],
            options={
                'verbose_name': 'Product Option Group',
                'verbose_name_plural': 'Product Option Groups',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ProductOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Jaise: Large, Extra cheese', max_length=60)),
                ('extra_price', models.DecimalField(decimal_places=2, default=0, help_text='Product ki price mein itni raqam jur jayegi (0 = muft)', max_digits=10)),
                ('is_available', models.BooleanField(default=True, help_text='OFF = abhi khatam, customer ko nazar aayega par chun nahi sakega')),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='app.productoptiongroup')),
            ],
            options={
                'verbose_name': 'Product Option',
                'verbose_name_plural': 'Product Options',
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
