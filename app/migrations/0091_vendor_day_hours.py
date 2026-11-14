from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0090_vendor_staff_extra_stores'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorDayHours',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.PositiveSmallIntegerField(help_text='0 = Monday ... 6 = Sunday')),
                ('is_closed', models.BooleanField(default=False, help_text='Is din store band')),
                ('opens_at', models.TimeField(blank=True, null=True)),
                ('closes_at', models.TimeField(blank=True, null=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='day_hours', to='app.vendorprofile')),
            ],
            options={'ordering': ['weekday'], 'unique_together': {('store', 'weekday')}},
        ),
    ]
