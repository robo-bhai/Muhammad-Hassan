from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0056_favorites'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='paused_until',
            field=models.DateTimeField(blank=True, help_text='Busy mode: is waqt tak naye orders band (khud khul jata hai). Khali = pause nahi.', null=True),
        ),
    ]
