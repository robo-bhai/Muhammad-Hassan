from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0089_vendor_branches'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorstaff',
            name='extra_stores',
            field=models.ManyToManyField(blank=True, help_text='Staff in branches par bhi kaam karta hai (orders, notifications, switch)', related_name='extra_staff', to='app.vendorprofile'),
        ),
    ]
