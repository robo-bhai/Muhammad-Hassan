"""Blacklist: suspend ke saath phone / email / device block, taake naya account na ban sake."""
from django.db import models


class BlockedIdentity(models.Model):
    KIND_PHONE = 'phone'
    KIND_EMAIL = 'email'
    KIND_DEVICE = 'device'
    KIND_CHOICES = [
        (KIND_PHONE, 'Phone'),
        (KIND_EMAIL, 'Email'),
        (KIND_DEVICE, 'Device (IP + browser)'),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, db_index=True)
    # phone -> phone_key (sirf digits, 92...), email -> chhote harf, device -> HMAC hash
    value = models.CharField(max_length=128, db_index=True)
    label = models.CharField(max_length=120, blank=True, default='', help_text='Dikhane ke liye (asli phone/email)')
    reason = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(max_length=12, blank=True, default='manual')     # customer / vendor / manual
    source_ref = models.CharField(max_length=40, blank=True, default='', db_index=True)   # customer:12 / vendor:5
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['kind', 'value'], name='uniq_blocked_kind_value')]
        verbose_name = 'Blocked identity'
        verbose_name_plural = 'Blocked identities'

    def __str__(self):
        return f'{self.get_kind_display()}: {self.label or self.value}'
