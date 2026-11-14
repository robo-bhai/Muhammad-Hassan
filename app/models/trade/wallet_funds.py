"""Models: trade/wallet_funds - wallet top-up requests aur gift cards.

Paisa shop khud leta hai (JazzCash / EasyPaisa / bank), online gateway nahi. Customer request bhejta hai
(raqam + transaction ID); admin payment dekh kar Approve karta hai:
    kind 'topup' -> customer ke wallet mein seedha jama (WalletTransaction 'topup')
    kind 'gift'  -> gift card ka code banta hai; khareedne wala usay kisi ko bhej sakta hai
Gift card ka code redeem karne par raqam redeem karne wale ke wallet mein jati hai (ek hi dafa).
"""
from django.db import models


class GiftCard(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('redeemed', 'Redeemed'), ('cancelled', 'Cancelled')]

    code = models.CharField(max_length=20, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Khali = kabhi expire nahi")
    buyer = models.ForeignKey('Customer', null=True, blank=True, on_delete=models.SET_NULL, related_name='gift_cards_bought')
    recipient_name = models.CharField(max_length=100, blank=True)
    message = models.CharField(max_length=200, blank=True)
    redeemed_by = models.ForeignKey('Customer', null=True, blank=True, on_delete=models.SET_NULL, related_name='gift_cards_redeemed')
    redeemed_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Gift Card'
        verbose_name_plural = 'Gift Cards'

    def __str__(self):
        return f"{self.code} ({self.amount}, {self.status})"


class WalletTopUp(models.Model):
    KIND_CHOICES = [('topup', 'Wallet top-up'), ('gift', 'Gift card purchase')]
    STATUS_CHOICES = [('pending', 'Pending (payment check hona baqi)'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    METHOD_CHOICES = [('jazzcash', 'JazzCash'), ('easypaisa', 'EasyPaisa'), ('bank', 'Bank transfer'), ('cash', 'Cash')]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='wallet_topups')
    kind = models.CharField(max_length=5, choices=KIND_CHOICES, default='topup')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default='jazzcash')
    reference = models.CharField(max_length=80, blank=True, help_text="Transaction ID / reference")
    recipient_name = models.CharField(max_length=100, blank=True)
    message = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True)
    gift_card = models.ForeignKey(GiftCard, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    admin_note = models.CharField(max_length=200, blank=True)
    reviewed_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Wallet Top-up Request'
        verbose_name_plural = 'Wallet Top-up Requests'
        indexes = [models.Index(fields=['status', 'created_at'], name='app_topup_status_idx')]

    def __str__(self):
        return f"{self.customer_id}: {self.amount} ({self.kind}, {self.status})"
