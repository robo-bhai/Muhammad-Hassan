"""Web Push subscriptions: ek user ke kayi browsers/phones ho sakte hain."""
import hashlib

from django.contrib.auth.models import User
from django.db import models


class PushSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.TextField()
    endpoint_hash = models.CharField(max_length=64, unique=True, editable=False)   # unique index (MySQL TextField par nahi lagta)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Push subscription'
        verbose_name_plural = 'Push subscriptions'
        ordering = ['-created_at']

    @staticmethod
    def hash_endpoint(endpoint):
        return hashlib.sha256((endpoint or '').encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        self.endpoint_hash = self.hash_endpoint(self.endpoint)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} - {self.endpoint[:40]}...'
