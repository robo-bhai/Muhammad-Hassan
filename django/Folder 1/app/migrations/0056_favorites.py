from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0055_menu_sections_popular_notes_subchoices'),
    ]

    operations = [
        migrations.CreateModel(
            name='FavoriteStore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorite_stores', to='app.customer')),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorited_by', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Favourite Store',
                'verbose_name_plural': 'Favourite Stores',
                'ordering': ['-created_at'],
                'unique_together': {('customer', 'store')},
            },
        ),
        migrations.CreateModel(
            name='WishlistItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wishlist_items', to='app.customer')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wishlisted_by', to='app.product')),
            ],
            options={
                'verbose_name': 'Wishlist Item',
                'verbose_name_plural': 'Wishlist Items',
                'ordering': ['-created_at'],
                'unique_together': {('customer', 'product')},
            },
        ),
    ]
