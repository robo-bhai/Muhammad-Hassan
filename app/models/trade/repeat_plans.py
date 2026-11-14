"""Models: trade/repeat_plans - customer ke daily / weekly repeat orders (doodh, sabzi jaisi cheezon ke liye)."""
from django.db import models


class RepeatOrderPlan(models.Model):
    DAILY, WEEKLY = 'daily', 'weekly'
    FREQUENCIES = [(DAILY, 'Every day'), (WEEKLY, 'Every week')]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='repeat_plans')
    source_order = models.ForeignKey('SaleOrder', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='repeat_plans',
                                     help_text="Is order ke items har baar cart mein aayenge")
    store_name = models.CharField(max_length=150, blank=True)
    summary = models.CharField(max_length=250, blank=True)
    frequency = models.CharField(max_length=10, choices=FREQUENCIES, default=DAILY)
    weekday = models.PositiveSmallIntegerField(default=0, help_text="Sirf weekly ke liye: 0=Monday ... 6=Sunday")
    time_of_day = models.TimeField(help_text="Is waqt customer ko yaad dihani aati hai")
    is_active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(db_index=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_active', 'next_run_at']
        verbose_name = 'Repeat Order Plan'
        verbose_name_plural = 'Repeat Order Plans'
        indexes = [models.Index(fields=['is_active', 'next_run_at'], name='app_repeat_active_next_idx')]

    def __str__(self):
        return f"{self.customer_id} {self.frequency} {self.time_of_day}"
