"""Suspend / unsuspend / approve / blacklist ki history: kis ne, kab, kyun."""
from django.db import models


class AccountActionLog(models.Model):
    KIND_CHOICES = [('customer', 'Customer'), ('vendor', 'Vendor'), ('other', 'Other')]
    ACTION_CHOICES = [
        ('suspend', 'Suspend'),
        ('unsuspend', 'Unsuspend'),
        ('approve', 'Approve'),
        ('block', 'Blacklist add'),
        ('unblock', 'Blacklist remove'),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, db_index=True)
    ref_id = models.PositiveIntegerField(null=True, blank=True, help_text='Customer ya Vendor ka id')
    name = models.CharField(max_length=150, blank=True, default='')            # us waqt ka naam (baad mein badal sakta hai)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, db_index=True)
    reason = models.CharField(max_length=255, blank=True, default='')
    detail = models.CharField(max_length=255, blank=True, default='')
    by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    by_name = models.CharField(max_length=150, blank=True, default='')         # user delete ho jaye tab bhi naam rahe
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Account action log'
        verbose_name_plural = 'Account action logs'

    def __str__(self):
        return f'{self.get_action_display()} - {self.name} ({self.created_at:%Y-%m-%d})'
