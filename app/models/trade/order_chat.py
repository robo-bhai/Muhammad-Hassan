"""Models: trade/order_chat - order ke andar customer <-> vendor / rider chat."""
from django.db import models


class OrderChatMessage(models.Model):
    CHANNELS = [('vendor', 'Customer <-> Vendor'), ('rider', 'Customer <-> Rider')]
    ROLES = [('customer', 'Customer'), ('vendor', 'Vendor'), ('rider', 'Rider')]

    order = models.ForeignKey('SaleOrder', on_delete=models.CASCADE, related_name='chat_messages')
    channel = models.CharField(max_length=10, choices=CHANNELS)
    sender_role = models.CharField(max_length=10, choices=ROLES)
    sender = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='order_chat_messages')
    message = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    # Dusre fareeq ne parh liya? (sender ke liye khud True)
    read_by_customer = models.BooleanField(default=False)
    read_by_other = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['order', 'channel', 'id'], name='app_ordchat_ord_chan_idx')]
        verbose_name = 'Order Chat Message'
        verbose_name_plural = 'Order Chat Messages'

    def __str__(self):
        return f"#{self.order_id} [{self.channel}] {self.sender_role}: {self.message[:40]}"
