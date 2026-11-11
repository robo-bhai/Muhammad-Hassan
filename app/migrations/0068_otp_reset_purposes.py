from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0067_cuisine_distance_fee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customerotp',
            name='purpose',
            field=models.CharField(
                choices=[
                    ('register', 'Registration'),
                    ('login', 'Login'),
                    ('forgot_password', 'Forgot Password'),
                    ('rider_reset', 'Rider Password Reset'),
                    ('admin_reset', 'Admin Password Reset'),
                    ('order', 'Order Verification'),
                ],
                default='register',
                max_length=20,
            ),
        ),
    ]
