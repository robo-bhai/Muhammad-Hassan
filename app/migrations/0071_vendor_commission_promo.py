from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0070_vendor_payout_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='commission_promo_percent',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Promo commission %',
                help_text="Launch offer: promo ki muddat me shop itna % rakhta hai (0 = commission-free). "
                          "Sirf tab lagta hai jab normal commission se kam ho aur 'Promo till' ki date na guzri ho."),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='commission_promo_until',
            field=models.DateField(
                blank=True, null=True, verbose_name='Promo till',
                help_text="Is date tak (is din samet) promo commission lagta hai. Date guzarne par normal rate "
                          "wapas aata hai (python manage.py expire_commission_promos roz chalayen)."),
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='launch_promo_granted_at',
            field=models.DateTimeField(
                blank=True, editable=False, null=True,
                help_text='Naye vendor ka launch offer ek hi dafa milta hai; ye us ka nishan hai.'),
        ),
    ]
