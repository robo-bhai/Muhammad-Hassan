from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0085_vendor_stock_controls'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiderBonus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('daily', 'Daily goal'), ('weekly', 'Weekly goal')], max_length=10)),
                ('period_start', models.DateField(help_text='Din ki tareekh, ya hafte ka Peer (Monday)')),
                ('deliveries', models.PositiveIntegerField(default=0, help_text='Target poora karte waqt deliveries')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bonuses', to='app.riderprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='riderbonus',
            constraint=models.UniqueConstraint(fields=('rider', 'kind', 'period_start'), name='uniq_rider_bonus_period'),
        ),
    ]
