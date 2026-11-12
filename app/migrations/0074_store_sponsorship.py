import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0073_enable_pro_loyalty'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreSponsorship',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending (payment ka intezar)'), ('active', 'Active'), ('cancelled', 'Cancelled')], default='pending', max_length=10)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('starts_on', models.DateField(blank=True, null=True)),
                ('ends_on', models.DateField(blank=True, help_text='Is din tak (wo din samet) store upar rahega', null=True)),
                ('amount', models.DecimalField(decimal_places=2, default=0, help_text='Vendor se li gayi raqam (aap ki income ka record)', max_digits=10)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sponsorships', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Store Sponsorship',
                'verbose_name_plural': 'Store Sponsorships',
                'ordering': ['-requested_at'],
            },
        ),
    ]
