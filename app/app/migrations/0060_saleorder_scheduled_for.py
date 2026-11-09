from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0059_loyalty_points'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleorder',
            name='scheduled_for',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True,
                help_text='Customer ne order baad ke waqt ke liye rakha (khali = jaldi se jaldi)'),
        ),
    ]
