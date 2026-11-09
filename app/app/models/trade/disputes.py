"""Models: trade/disputes - customer ka order par dispute (masla) aur admin ka faisla.

Ek order par sirf ek dispute (OneToOne). Faisla: wallet mein full/partial refund ya reject.
Wallet refund WalletTransaction(kind='dispute') banata hai; (order, kind) unique hone ki wajah se
ek order par dispute refund do dafa nahi ho sakta.
"""
from decimal import Decimal

from django.db import models


class OrderDispute(models.Model):
    REASON_CHOICES = [
        ('missing_item', 'Item missing'),
        ('wrong_item', 'Wrong item'),
        ('bad_quality', 'Bad quality / damaged'),
        ('late', 'Very late delivery'),
        ('not_received', 'Order not received'),
        ('extra_charge', 'Extra charge'),
        ('rider_behavior', 'Rider behaviour'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('under_review', 'Under review'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]
    OPEN_STATUSES = ('open', 'under_review')
    RESOLUTION_CHOICES = [
        ('refund_full', 'Full refund to wallet'),
        ('refund_partial', 'Partial refund to wallet'),
        ('no_refund', 'No refund'),
    ]

    sale_order = models.OneToOneField('SaleOrder', on_delete=models.CASCADE, related_name='dispute')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='disputes')
    vendor = models.ForeignKey('Vendor', null=True, blank=True, on_delete=models.SET_NULL, related_name='disputes')
    rider = models.ForeignKey('RiderProfile', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='disputes')

    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField(blank=True, default='')
    photo = models.ImageField(upload_to='disputes/%Y/%m/', null=True, blank=True)

    # Vendor / rider ka jawab (har ek sirf ek dafa, jab tak dispute open hai)
    vendor_response = models.TextField(blank=True, default='')
    vendor_photo = models.ImageField(upload_to='disputes/%Y/%m/', null=True, blank=True)
    vendor_responded_at = models.DateTimeField(null=True, blank=True)
    rider_response = models.TextField(blank=True, default='')
    rider_photo = models.ImageField(upload_to='disputes/%Y/%m/', null=True, blank=True)
    rider_responded_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open', db_index=True)
    resolution = models.CharField(max_length=15, choices=RESOLUTION_CHOICES, blank=True, default='')
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    admin_note = models.CharField(max_length=300, blank=True, default='',
                                  help_text="Customer ko dikhne wala jawab")
    resolved_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='+')
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Order Dispute'
        verbose_name_plural = 'Order Disputes'
        indexes = [models.Index(fields=['status', 'created_at'], name='dispute_status_created_idx')]

    def __str__(self):
        return f"Dispute #{self.pk} - order {self.sale_order_id} ({self.status})"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES
