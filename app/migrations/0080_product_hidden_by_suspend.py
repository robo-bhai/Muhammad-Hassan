from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0079_accountactionlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='hidden_by_suspend',
            field=models.BooleanField(default=False),
        ),
    ]
