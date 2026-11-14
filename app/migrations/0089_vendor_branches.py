from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0088_vendor_staff'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='parent',
            field=models.ForeignKey(blank=True, help_text='Khali = main store. Bhara = ye is store ki branch hai.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='branches', to='app.vendorprofile'),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='branch_name',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
    ]
