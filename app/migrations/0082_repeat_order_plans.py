from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0081_wishlist_alerts_order_chat'),
    ]

    operations = [
        migrations.CreateModel(
            name='RepeatOrderPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('store_name', models.CharField(blank=True, max_length=150)),
                ('summary', models.CharField(blank=True, max_length=250)),
                ('frequency', models.CharField(choices=[('daily', 'Every day'), ('weekly', 'Every week')], default='daily', max_length=10)),
                ('weekday', models.PositiveSmallIntegerField(default=0, help_text='Sirf weekly ke liye: 0=Monday ... 6=Sunday')),
                ('time_of_day', models.TimeField(help_text='Is waqt customer ko yaad dihani aati hai')),
                ('is_active', models.BooleanField(default=True)),
                ('next_run_at', models.DateTimeField(db_index=True)),
                ('last_notified_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='repeat_plans', to='app.customer')),
                ('source_order', models.ForeignKey(blank=True, help_text='Is order ke items har baar cart mein aayenge', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='repeat_plans', to='app.saleorder')),
            ],
            options={'verbose_name': 'Repeat Order Plan', 'verbose_name_plural': 'Repeat Order Plans', 'ordering': ['-is_active', 'next_run_at']},
        ),
        migrations.AddIndex(model_name='repeatorderplan',
                            index=models.Index(fields=['is_active', 'next_run_at'], name='app_repeat_active_next_idx')),
    ]
