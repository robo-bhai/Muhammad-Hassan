"""Delivery models."""
import os
import uuid

from django.db import models
from decimal import Decimal
from app.security.field_crypto import EncryptedCharField, EncryptedTextField

class DeliverySettings(models.Model):
    """Delivery settings — admin configurable"""
    
    # Standard delivery
    standard_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('100.00'),
        verbose_name="Standard Delivery Charge (Rs.)"
    )
    standard_delivery_time = models.CharField(
        max_length=100, 
        default="2-4 working days",
        verbose_name="Standard Delivery Time"
    )
    
    # Express delivery
    express_delivery_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable Express Delivery"
    )
    express_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('300.00'),
        verbose_name="Express Delivery Charge (Rs.)"
    )
    express_delivery_time = models.CharField(
        max_length=100, 
        default="Same day (within city)",
        verbose_name="Express Delivery Time"
    )
    
    # Store pickup
    store_pickup_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable Store Pickup"
    )
    
    # Free delivery
    free_delivery_enabled = models.BooleanField(
        default=True,
        verbose_name="Enable Free Delivery Threshold"
    )
    free_delivery_threshold = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('1000.00'),
        verbose_name="Free Delivery Threshold (Rs.)"
    )
    
    # City-based charges
    city_charges = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="City-wise Delivery Charges",
        help_text='Format: {"karachi": 100, "lahore": 120, "other": 200}'
    )
    
    # Meta
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "🚚 Delivery Settings"
        verbose_name_plural = "🚚 Delivery Settings"
    
    def __str__(self):
        return f"Delivery Settings (Rs. {self.standard_charge})"
    
    def save(self, *args, **kwargs):
        # Only one active
        if self.is_active:
            DeliverySettings.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class RiderProfile(models.Model):
    """Rider ka login account (Talabat rider app jaisa). Admin banata hai."""
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='rider_profile'
    )
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, unique=True)
    vehicle = models.CharField(max_length=50, blank=True, default='')
    is_active = models.BooleanField(default=True)
    is_online = models.BooleanField(default=False, help_text="Rider abhi orders lene ke liye tayyar hai")
    per_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=50,
                                           help_text="Har delivery par rider ki kamai (Rs.)")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    # Onboarding: purane riders 'approved' rehte hain; naye (documents wale) 'pending' se shuru hote hain
    APPROVAL = [('pending', 'Review mein'), ('approved', 'Approved'), ('rejected', 'Rad'), ('suspended', 'Suspended')]
    approval_status = models.CharField(max_length=10, choices=APPROVAL, default='approved', db_index=True)
    approval_note = models.CharField(max_length=200, blank=True, default='')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "🏍️ Riders"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone})"


class RiderSettlement(models.Model):
    """Rider ke saath hisab: COD cash jama (cash_in) ya kamai ki ada'egi (payout)."""
    KINDS = [('cash_in', 'Cash jama (rider se liya)'), ('payout', 'Kamai ada ki (rider ko di)')]
    rider = models.ForeignKey(RiderProfile, on_delete=models.CASCADE, related_name='settlements')
    kind = models.CharField(max_length=10, choices=KINDS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rider.name} {self.kind} Rs.{self.amount}"


def rider_doc_path(instance, filename):
    """Documents ka naam anjaan (uuid) rakhte hain taake URL andaze se na milay."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.pdf'):
        ext = '.bin'
    return f'rider_docs/{instance.rider_id}/{uuid.uuid4().hex}{ext}'


class RiderDocument(models.Model):
    """Rider ka ek document (CPR, licence, vehicle, photo). Har rider ka har kind ka ek hi record."""
    STATUS = [('pending', 'Review mein'), ('approved', 'Approved'), ('rejected', 'Rad')]
    rider = models.ForeignKey(RiderProfile, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=10)
    file = models.FileField(upload_to=rider_doc_path)
    number = models.CharField(max_length=40, blank=True, default='')
    expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    reject_reason = models.CharField(max_length=200, blank=True, default='')
    reviewed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rider_id', 'kind']
        constraints = [models.UniqueConstraint(fields=['rider', 'kind'], name='uniq_rider_document_kind')]

    def __str__(self):
        return f"{self.rider.name} {self.kind} ({self.status})"


class RiderShift(models.Model):
    """Admin ki banayi shift (waqt ka slot). Riders capacity tak book kar sakte hain."""
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(help_text="Shuru se pehle ho to shift agle din khatam hoti hai")
    capacity = models.PositiveSmallIntegerField(default=5)
    zone = models.CharField(max_length=60, blank=True, default='')
    is_open = models.BooleanField(default=True, help_text="Band ho to nayi booking nahi")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'start_time']
        constraints = [models.UniqueConstraint(fields=['date', 'start_time', 'end_time', 'zone'],
                                               name='uniq_rider_shift_slot')]

    def __str__(self):
        return f"{self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M} {self.zone}".strip()


class RiderShiftBooking(models.Model):
    STATUS = [('booked', 'Booked'), ('cancelled', 'Cancelled')]
    shift = models.ForeignKey(RiderShift, on_delete=models.CASCADE, related_name='bookings')
    rider = models.ForeignKey(RiderProfile, on_delete=models.CASCADE, related_name='shift_bookings')
    status = models.CharField(max_length=10, choices=STATUS, default='booked')
    booked_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['shift', 'rider'], name='uniq_rider_shift_booking')]

    def __str__(self):
        return f"{self.rider.name} -> {self.shift} ({self.status})"


class RiderBonus(models.Model):
    """Goal bonus: rider ne din/hafte ka target poora kiya. Har (rider, kind, period_start) ek hi baar milta hai."""
    KINDS = [('daily', 'Daily goal'), ('weekly', 'Weekly goal')]
    rider = models.ForeignKey(RiderProfile, on_delete=models.CASCADE, related_name='bonuses')
    kind = models.CharField(max_length=10, choices=KINDS)
    period_start = models.DateField(help_text="Din ki tareekh, ya hafte ka Peer (Monday)")
    deliveries = models.PositiveIntegerField(default=0, help_text="Target poora karte waqt deliveries")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['rider', 'kind', 'period_start'], name='uniq_rider_bonus_period')]

    def __str__(self):
        return f"{self.rider.name} {self.kind} bonus Rs.{self.amount}"


class OrderReview(models.Model):
    """Customer ki rating: store (vendor) aur rider ke liye (delivered order par, ek dafa)."""
    sale_order = models.OneToOneField('SaleOrder', on_delete=models.CASCADE, related_name='review')
    vendor = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    rider = models.ForeignKey(RiderProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    vendor_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    vendor_comment = models.CharField(max_length=300, blank=True, default='')
    rider_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rider_comment = models.CharField(max_length=300, blank=True, default='')
    vendor_reply = models.CharField(max_length=300, blank=True, default='',
                                    help_text="Store ka public jawab (customer aur store page par dikhta hai)")
    vendor_replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review {self.sale_order_id}: store {self.vendor_rating} / rider {self.rider_rating}"


class DeliveryInfo(models.Model):
    """Delivery type aur rider/pickup info"""
    
    DELIVERY_TYPES = [
        ('local_rider', '🏍️ Local Rider'),
        ('customer_pickup', '🚶 Customer Pickup'),
    ]
    
    STATUS_CHOICES = [
        ('pending', '⏳ Pending'),
        ('assigned', '✅ Assigned'),
        ('picked_up', '📦 Picked Up'),
        ('in_transit', '🛵 In Transit'),
        ('delivered', '🎉 Delivered'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Link to order
    order = models.OneToOneField(
        'CustomerOrder',
        on_delete=models.CASCADE,
        related_name='delivery_info',
        null=True, blank=True
    )
    sale_order = models.OneToOneField(
        'SaleOrder',
        on_delete=models.CASCADE,
        related_name='delivery_info',
        null=True, blank=True
    )
    
    # Delivery type
    delivery_type = models.CharField(
        max_length=20,
        choices=DELIVERY_TYPES,
        default='local_rider'
    )
    
    # Rider Info (if local_rider)
    rider = models.ForeignKey(
        'RiderProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deliveries',
        verbose_name="Rider (login wala)"
    )
    rider_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                    help_text="Is delivery par rider ki kamai")
    cash_collected = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                         help_text="COD cash jo rider ne customer se liya")
    rider_name = models.CharField(max_length=100, blank=True, null=True)
    rider_contact = models.CharField(max_length=20, blank=True, null=True)
    rider_vehicle = models.CharField(max_length=50, blank=True, null=True)
    rider_cnic = EncryptedCharField(max_length=20, blank=True, null=True)
    
    # Pickup Info (if customer_pickup)
    pickup_location = models.TextField(blank=True, null=True)
    pickup_ready_at = models.DateTimeField(null=True, blank=True)
    pickup_notes = models.CharField(max_length=255, blank=True, null=True)
    
    # Delivery proof
    delivery_photo = models.ImageField(
        upload_to='delivery_proof/%Y/%m/',
        null=True, blank=True,
        verbose_name="Delivery Proof Photo"
    )
    delivery_signature = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Receiver Name/Signature"
    )
    delivery_notes = models.TextField(blank=True, null=True)
    
    # Timing
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    expected_delivery = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # System
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_deliveries'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "🚚 Delivery Info"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['delivery_type']),
        ]
    
    def __str__(self):
        order_no = ''
        if self.order:
            order_no = self.order.order_number
        elif self.sale_order:
            order_no = self.sale_order.order_no
        return f"Delivery for {order_no} - {self.get_delivery_type_display()}"
    
    @property
    def order_number(self):
        """Get order number regardless of type"""
        if self.order:
            return self.order.order_number
        elif self.sale_order:
            return self.sale_order.order_no
        return "N/A"
    
    @property
    def customer(self):
        """Get customer regardless of type"""
        if self.order:
            return self.order.customer
        elif self.sale_order:
            return self.sale_order.customer
        return None
    
    @property
    def status_badge(self):
        colors = {
            'pending': 'secondary',
            'assigned': 'info',
            'picked_up': 'primary',
            'in_transit': 'warning',
            'delivered': 'success',
            'cancelled': 'danger',
        }
        return f'<span class="badge bg-{colors.get(self.status, "secondary")}">{self.get_status_display()}</span>'


class OrderTracking(models.Model):
    """Record of every movement of the order (Timeline)"""
    
    STATUS_CHOICES = [
        ('confirmed', '✅ Confirmed'),
        ('processing', '⚙️ Processing'),
        ('packed', '📦 Packed'),
        ('rider_assigned', '🏍️ Rider Assigned'),
        ('ready_for_pickup', '🚶 Ready for Pickup'),
        ('out_for_delivery', '🛵 Out for Delivery'),
        ('delivered', '🎉 Delivered'),
        ('picked_up', '✋ Picked Up by Customer'),
        ('cancelled', '❌ Cancelled'),
    ]
    
    # Order link
    order = models.ForeignKey(
        'CustomerOrder',
        on_delete=models.CASCADE,
        related_name='tracking_history',
        null=True, blank=True
    )
    sale_order = models.ForeignKey(
        'SaleOrder',
        on_delete=models.CASCADE,
        related_name='tracking_history',
        null=True, blank=True
    )
    
    # Status
    status = models.CharField(max_length=25, choices=STATUS_CHOICES)
    title = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    # Location & Notes
    location = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Proof
    proof_photo = models.ImageField(
        upload_to='tracking_proof/%Y/%m/',
        null=True, blank=True
    )
    
    # Rider info snapshot (at time of this update)
    rider_name = models.CharField(max_length=100, blank=True, null=True)
    rider_contact = models.CharField(max_length=20, blank=True, null=True)
    
    # GPS (optional)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # WhatsApp status
    whatsapp_sent = models.BooleanField(default=False)
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True)
    
    # System
    updated_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='order_tracking_updates'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "📍 Order Tracking"
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['order', '-timestamp']),
            models.Index(fields=['sale_order', '-timestamp']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        order_no = ''
        if self.order:
            order_no = self.order.order_number
        elif self.sale_order:
            order_no = self.sale_order.order_no
        return f"{order_no} - {self.get_status_display()}"
    
    @property
    def order_number(self):
        if self.order:
            return self.order.order_number
        elif self.sale_order:
            return self.sale_order.order_no
        return "N/A"
    
    @property
    def icon(self):
        icons = {
            'confirmed': '✅',
            'processing': '⚙️',
            'packed': '📦',
            'rider_assigned': '🏍️',
            'ready_for_pickup': '🚶',
            'out_for_delivery': '🛵',
            'delivered': '🎉',
            'picked_up': '✋',
            'cancelled': '❌',
        }
        return icons.get(self.status, '📌')
    
    @property
    def color(self):
        colors = {
            'confirmed': 'success',
            'processing': 'info',
            'packed': 'primary',
            'rider_assigned': 'info',
            'ready_for_pickup': 'warning',
            'out_for_delivery': 'warning',
            'delivered': 'success',
            'picked_up': 'success',
            'cancelled': 'danger',
        }
        return colors.get(self.status, 'secondary')


class DeliveryFeedback(models.Model):
    """Customer ka delivery feedback"""
    
    RATING_CHOICES = [(i, f'{i} ⭐') for i in range(1, 6)]
    
    order = models.OneToOneField(
        'CustomerOrder',
        on_delete=models.CASCADE,
        related_name='delivery_feedback',
        null=True, blank=True
    )
    
    rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    comment = models.TextField(blank=True, null=True)
    
    # Separate ratings
    rider_rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    speed_rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    packaging_rating = models.PositiveIntegerField(choices=RATING_CHOICES, default=5)
    
    would_recommend = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "⭐ Delivery Feedback"
    
    def __str__(self):
        return f"{self.order.order_number if self.order else 'N/A'} - {self.rating}⭐"


class DispatchAttempt(models.Model):
    """Auto dispatch: kis rider ko kis tarteeb se order offer hua."""
    sale_order = models.OneToOneField('SaleOrder', on_delete=models.CASCADE, related_name='dispatch_attempt')
    ranking = models.JSONField(default=list)     # rider ids, offer ki tarteeb mein
    declined = models.JSONField(default=list)    # riders jinhon ne reject kiya
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "🎯 Dispatch"
