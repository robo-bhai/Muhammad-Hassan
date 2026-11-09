"""Models: trade/coupon - promo codes / store offers (Talabat jaise).

Coupon: admin banata hai. Percent ya fixed discount, optional store, date range, usage limits.
CouponRedemption: har order par kitna discount laga (limits ginne aur report ke liye).

Discount SaleOrder.discount_value mein jata hai (isi se total, invoice aur vendor ka hissa chalta hai).
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Q
from django.utils import timezone

CENT = Decimal('0.01')


class Coupon(models.Model):
    TYPE_PERCENT = 'percent'
    TYPE_FIXED = 'fixed'
    TYPES = [(TYPE_PERCENT, 'Percent (%)'), (TYPE_FIXED, 'Fixed amount')]

    code = models.CharField(max_length=30, unique=True, help_text="Customer yeh code likhta hai (jaise WELCOME20). Capital mein save hota hai")
    title = models.CharField(max_length=80, help_text="Store card par badge: jaise '20% off' ya 'Rs 100 off'. Khali = khud ban jata hai", blank=True, default='')
    discount_type = models.CharField(max_length=7, choices=TYPES, default=TYPE_PERCENT)
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Percent ho to 1-100, fixed ho to raqam")
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       help_text="Percent coupon ki hadd (khali = koi hadd nahi)")
    min_order = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Kam az kam order (items ka subtotal)")
    store = models.ForeignKey('VendorProfile', null=True, blank=True, on_delete=models.CASCADE, related_name='coupons',
                              help_text="Khali = har store par chalega. Store chunein to sirf us store par")
    show_on_store = models.BooleanField(default=True, help_text="ON = store card/page par offer badge dikhao (sirf store wale coupon ka)")
    first_order_only = models.BooleanField(default=False, help_text="Sirf customer ke pehle order par")
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Kul kitni dafa use ho sakta hai (khali = bepanah)")
    per_customer_limit = models.PositiveIntegerField(default=1, help_text="Ek customer kitni dafa (0 = bepanah)")
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Coupon'
        verbose_name_plural = 'Coupons'
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper().replace(' ', '')
        super().save(*args, **kwargs)

    # ---- display ----
    @property
    def badge(self):
        if self.title:
            return self.title
        v = self.value.normalize() if self.value == self.value.to_integral() else self.value
        return f"{v}% off" if self.discount_type == self.TYPE_PERCENT else f"{v} off"

    # ---- state ----
    @classmethod
    def live(cls):
        today = timezone.localdate()
        return (cls.objects.filter(is_active=True)
                .filter(Q(starts_on__isnull=True) | Q(starts_on__lte=today))
                .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=today)))

    @property
    def status(self):
        today = timezone.localdate()
        if not self.is_active:
            return 'off'
        if self.starts_on and self.starts_on > today:
            return 'scheduled'
        if self.ends_on and self.ends_on < today:
            return 'expired'
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return 'used_up'
        return 'live'

    @property
    def used_count(self):
        # Cancel hue order ka istemal gina nahi jata (coupon wapas mil jata hai)
        return self.redemptions.exclude(order__status='cancelled').count()

    def compute(self, subtotal):
        """Is subtotal par kitna discount banta hai (subtotal se zyada kabhi nahi)."""
        subtotal = Decimal(subtotal or 0)
        if self.discount_type == self.TYPE_PERCENT:
            amt = (subtotal * Decimal(self.value) / Decimal(100)).quantize(CENT, ROUND_HALF_UP)
            if self.max_discount:
                amt = min(amt, Decimal(self.max_discount))
        else:
            amt = Decimal(self.value)
        return max(Decimal('0.00'), min(amt, subtotal)).quantize(CENT, ROUND_HALF_UP)


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='redemptions')
    order = models.OneToOneField('SaleOrder', on_delete=models.CASCADE, related_name='coupon_redemption')
    customer = models.ForeignKey('Customer', null=True, blank=True, on_delete=models.SET_NULL, related_name='coupon_redemptions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.coupon.code} -> {self.order_id} ({self.amount})"
