"""Models: trade/offers - Wallet credit (+ cashback rewards) aur Pro membership (free delivery).

WalletTransaction: customer ke wallet ka khata. amount + ho to jama, - ho to kharch.
    balance = sab transactions ka jod. Ek order par ek hi 'spend', 'refund' aur 'cashback' ban sakta hai
    (isi se signal dobara chalne par paisa do baar nahi lagta).
    Referral: ek hi order par referrer ('referral') aur referee ('refbonus') dono ko reward milta hai,
    isi liye do alag kind hain (warna (order, kind) unique constraint dusra insert rok deta).
ProMembership: customer ki Pro request/membership. Admin payment mil jane par Activate karta hai.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone


class WalletTransaction(models.Model):
    KIND_CHOICES = [
        ('topup', 'Top-up (admin ne jama kiya)'),
        ('adjust', 'Adjustment (admin)'),
        ('spend', 'Order mein kharch'),
        ('refund', 'Order cancel - wapas'),
        ('cashback', 'Cashback reward'),
        ('points', 'Loyalty points se credit'),
        ('pro', 'Pro membership ki payment'),
        ('dispute', 'Dispute refund'),
        ('referral', 'Referral reward (dost laaya)'),
        ('refbonus', 'Referral welcome bonus'),
        ('giftcard', 'Gift card redeem'),
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='wallet_transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="+ jama, - kharch")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    order = models.ForeignKey('SaleOrder', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='wallet_transactions')
    note = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Wallet Transaction'
        verbose_name_plural = 'Wallet Transactions'
        constraints = [
            models.UniqueConstraint(fields=['order', 'kind'], condition=Q(order__isnull=False),
                                    name='wallet_one_per_order_kind'),
        ]
        indexes = [models.Index(fields=['customer', 'created_at'], name='wallet_cust_created_idx')]

    def __str__(self):
        return f"{self.customer_id}: {self.amount} ({self.kind})"


class ProMembership(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending (payment ka intezar)'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='pro_memberships')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                 help_text="Customer se li gayi raqam (record ke liye)")
    note = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Pro Membership'
        verbose_name_plural = 'Pro Memberships'

    def __str__(self):
        return f"Pro {self.customer_id} ({self.status})"

    @property
    def is_running(self):
        """Abhi chal rahi hai? (active aur mudat baqi)"""
        return self.status == 'active' and bool(self.ends_on) and self.ends_on >= timezone.localdate()

    def activate(self, days):
        """Aaj se `days` din ke liye chalu karo (pehle se chalti ho to us ke baad se barhao)."""
        today = timezone.localdate()
        from datetime import timedelta
        base = today
        running = (ProMembership.objects.filter(customer=self.customer, status='active', ends_on__gte=today)
                   .exclude(pk=self.pk).order_by('-ends_on').first())
        if running:                      # pehle se chal rahi membership ke baad se shuru
            base = running.ends_on + timedelta(days=1)
        self.starts_on = base
        self.ends_on = base + timedelta(days=max(int(days), 1) - 1)
        self.status = 'active'
        self.save()


class LoyaltyTransaction(models.Model):
    """Loyalty points ka khata. points + ho to mile, - ho to kharch (wallet credit mein badle).
    Ek order par 'earn' sirf ek dafa ban sakta hai."""
    KIND_CHOICES = [
        ('earn', 'Order par points mile'),
        ('redeem', 'Wallet credit mein badle'),
        ('adjust', 'Adjustment (admin)'),
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='loyalty_transactions')
    points = models.IntegerField(help_text="+ mile, - kharch")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES)
    order = models.ForeignKey('SaleOrder', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='loyalty_transactions')
    note = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Loyalty Points Entry'
        verbose_name_plural = 'Loyalty Points'
        constraints = [
            models.UniqueConstraint(fields=['order', 'kind'], condition=Q(order__isnull=False),
                                    name='loyalty_one_per_order_kind'),
        ]
        indexes = [models.Index(fields=['customer', 'created_at'], name='loyalty_cust_created_idx')]

    def __str__(self):
        return f"{self.customer_id}: {self.points} ({self.kind})"


class Referral(models.Model):
    """Customer referral: referrer ne referee ko bulaya.

    Referee ke register hone par 'pending' banta hai. Reward (wallet credit, dono ko) tab milta hai jab
    referee ka PEHLA order delivered ho aur minimum amount ka ho. Referee sirf ek dafa refer ho sakta hai (OneToOne).
    """
    STATUS_CHOICES = [
        ('pending', 'Pending (pehle order ka intezar)'),
        ('rewarded', 'Rewarded'),
        ('rejected', 'Rejected'),
    ]

    referrer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='referrals_made')
    referee = models.OneToOneField('Customer', on_delete=models.CASCADE, related_name='referral_received')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reject_reason = models.CharField(max_length=120, blank=True, default='')
    device_hash = models.CharField(max_length=64, blank=True, default='', db_index=True,
                                   help_text="Register ke waqt IP + browser ka hash (asal IP save nahi hota)")
    reward_order = models.ForeignKey('SaleOrder', null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+', help_text="Jis order par reward mila")
    referrer_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    referee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    rewarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Referral'
        verbose_name_plural = 'Referrals'
        indexes = [models.Index(fields=['referrer', 'status', 'rewarded_at'], name='referral_ref_status_idx')]

    def __str__(self):
        return f"{self.referrer_id} -> {self.referee_id} ({self.status})"
