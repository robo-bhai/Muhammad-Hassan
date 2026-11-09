"""
Address / CNIC fields ko encrypted fields mein badalta hai (varchar/text -> text).
Purana data wahi rehta hai (plaintext parha jata hai). Purane rows ko encrypt karne ke liye:
    python manage.py encrypt_existing_data
"""
from django.db import migrations

import app.security.field_crypto


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0048_storecategory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customeraddress', name='address_line_1',
            field=app.security.field_crypto.EncryptedCharField(max_length=255)),
        migrations.AlterField(
            model_name='customeraddress', name='address_line_2',
            field=app.security.field_crypto.EncryptedCharField(blank=True, max_length=255, null=True)),
        migrations.AlterField(
            model_name='customeraddress', name='landmark',
            field=app.security.field_crypto.EncryptedCharField(blank=True, max_length=200, null=True)),
        migrations.AlterField(
            model_name='customerorder', name='shipping_address',
            field=app.security.field_crypto.EncryptedTextField()),
        migrations.AlterField(
            model_name='customerorder', name='shipping_landmark',
            field=app.security.field_crypto.EncryptedCharField(blank=True, max_length=200, null=True)),
        migrations.AlterField(
            model_name='customerorder', name='billing_address',
            field=app.security.field_crypto.EncryptedTextField(blank=True, null=True)),
        migrations.AlterField(
            model_name='deliveryinfo', name='rider_cnic',
            field=app.security.field_crypto.EncryptedCharField(blank=True, max_length=20, null=True)),
        migrations.AlterField(
            model_name='customer', name='address',
            field=app.security.field_crypto.EncryptedTextField(blank=True, null=True)),
    ]
