from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0064_rider_live_location'),
    ]

    operations = [
        migrations.AddField(model_name='vendorprofile', name='lat',
                            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
        migrations.AddField(model_name='vendorprofile', name='lng',
                            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
        migrations.CreateModel(
            name='DispatchAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ranking', models.JSONField(default=list)),
                ('declined', models.JSONField(default=list)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('sale_order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                    related_name='dispatch_attempt', to='app.saleorder')),
            ],
            options={'verbose_name_plural': '🎯 Dispatch'},
        ),
    ]
