import app.models.trade.vendor_portal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0091_vendor_day_hours'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=10)),
                ('file', models.FileField(upload_to=app.models.trade.vendor_portal.vendor_doc_path)),
                ('number', models.CharField(blank=True, default='', max_length=40)),
                ('expiry', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Under review'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=10)),
                ('reject_reason', models.CharField(blank=True, default='', max_length=200)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('uploaded_at', models.DateTimeField(auto_now=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='app.vendorprofile')),
            ],
            options={'ordering': ['store_id', 'kind']},
        ),
        migrations.AddConstraint(
            model_name='vendordocument',
            constraint=models.UniqueConstraint(fields=('store', 'kind'), name='uniq_vendor_document_kind'),
        ),
    ]
