"""Models: trade/favorites - customer ke pasandida stores aur wishlist (pasandida items)."""
from django.db import models

from ..inventory.catalog import Product


class FavoriteStore(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='favorite_stores')
    store = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'store')
        ordering = ['-created_at']
        verbose_name = 'Favourite Store'
        verbose_name_plural = 'Favourite Stores'

    def __str__(self):
        return f"{self.customer_id} -> {self.store_id}"


class WishlistItem(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'product')
        ordering = ['-created_at']
        verbose_name = 'Wishlist Item'
        verbose_name_plural = 'Wishlist Items'

    def __str__(self):
        return f"{self.customer_id} -> {self.product_id}"
