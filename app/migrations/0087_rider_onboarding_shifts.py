import app.models.trade.delivery
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0086_rider_bonus'),
    ]

    operations = [
        migrations.AddField(
            model_name='riderprofile',
            name='approval_status',
            field=models.CharField(choices=[('pending', 'Review mein'), ('approved', 'Approved'), ('rejected', 'Rad'), ('suspended', 'Suspended')], db_index=True, default='approved', max_length=10),
        ),
        migrations.AddField(
            model_name='riderprofile',
            name='approval_note',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='riderprofile',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='RiderDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=10)),
                ('file', models.FileField(upload_to=app.models.trade.delivery.rider_doc_path)),
                ('number', models.CharField(blank=True, default='', max_length=40)),
                ('expiry', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Review mein'), ('approved', 'Approved'), ('rejected', 'Rad')], default='pending', max_length=10)),
                ('reject_reason', models.CharField(blank=True, default='', max_length=200)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('uploaded_at', models.DateTimeField(auto_now=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='app.riderprofile')),
            ],
            options={'ordering': ['rider_id', 'kind']},
        ),
        migrations.AddConstraint(
            model_name='riderdocument',
            constraint=models.UniqueConstraint(fields=('rider', 'kind'), name='uniq_rider_document_kind'),
        ),
        migrations.CreateModel(
            name='RiderShift',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField(help_text='Shuru se pehle ho to shift agle din khatam hoti hai')),
                ('capacity', models.PositiveSmallIntegerField(default=5)),
                ('zone', models.CharField(blank=True, default='', max_length=60)),
                ('is_open', models.BooleanField(default=True, help_text='Band ho to nayi booking nahi')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['date', 'start_time']},
        ),
        migrations.AddConstraint(
            model_name='ridershift',
            constraint=models.UniqueConstraint(fields=('date', 'start_time', 'end_time', 'zone'), name='uniq_rider_shift_slot'),
        ),
        migrations.CreateModel(
            name='RiderShiftBooking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('booked', 'Booked'), ('cancelled', 'Cancelled')], default='booked', max_length=10)),
                ('booked_at', models.DateTimeField(auto_now_add=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shift_bookings', to='app.riderprofile')),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='app.ridershift')),
            ],
        ),
        migrations.AddConstraint(
            model_name='ridershiftbooking',
            constraint=models.UniqueConstraint(fields=('shift', 'rider'), name='uniq_rider_shift_booking'),
        ),
    ]
