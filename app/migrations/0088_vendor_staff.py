from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0087_rider_onboarding_shifts'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorStaff',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('phone', models.CharField(db_index=True, help_text='Staff isi phone se login karta hai', max_length=20, unique=True)),
                ('role', models.CharField(choices=[('manager', 'Manager (products, offers, reports, orders)'), ('orders', 'Orders only (orders, busy mode)')], default='orders', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('last_login_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staff_members', to='app.vendorprofile')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vendor_staff', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-is_active', 'name']},
        ),
    ]
