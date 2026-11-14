"""Models: trade/vendor_portal - vendor self-service login (shop par products list karne ke liye)."""
from datetime import time

from django.db import models
from django.utils import timezone

from ..inventory.catalog import Category, Product


class StoreCategory(models.Model):
    """Store ki type (Restaurant, Grocery, Pharmacy...) - Talabat ke top icons jaisi.
    Ye PRODUCT category (Category model) se alag hai: ye poore store ko batati hai."""
    name = models.CharField(max_length=60, unique=True)
    icon = models.CharField(max_length=8, blank=True, default='🏪',
                            help_text="Ek emoji, jaise 🍔 🛒 💊")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Chhota number pehle nazar aata hai")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Store Category'
        verbose_name_plural = '3.1 Store Categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.icon} {self.name}".strip()


class Cuisine(models.Model):
    """Khane ki qism (Pizza, Burger, Biryani, BBQ...) - Talabat ke cuisine filter jaisi.
    StoreCategory se alag: StoreCategory store ki type (Restaurant/Grocery), Cuisine us store ka khana."""
    name = models.CharField(max_length=60, unique=True)
    icon = models.CharField(max_length=8, blank=True, default='🍽️', help_text="Ek emoji, jaise 🍕 🍔 🍛")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Chhota number pehle nazar aata hai")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Cuisine'
        verbose_name_plural = '3.1b Cuisines'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.icon} {self.name}".strip()


class DeliveryArea(models.Model):
    """Admin ki banayi hui areas ki master list (shehar -> area).
    Vendor aur customer isi list se chunte hain, is liye spelling ka masla nahi aata.
    VendorProfile.delivery_areas mein label ('Gulberg (Lahore)') text ki tarah save hota hai,
    is liye purana matching logic jyon ka tyon chalta hai."""
    city = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=100, help_text="Area, mohalla ya gaon ka naam")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Chhota number pehle nazar aata hai")
    is_active = models.BooleanField(default=True)
    extra_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Is area mein deliver karne par store ki fee ke upar extra (door ke areas ke liye). 0 = koi extra nahi.")

    class Meta:
        verbose_name = 'Delivery Area'
        verbose_name_plural = '3.3 Delivery Areas'
        ordering = ['city', 'sort_order', 'name']
        unique_together = [('city', 'name')]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return f"{self.name} ({self.city})"

    @classmethod
    def grouped(cls):
        """[(city, [DeliveryArea, ...]), ...] - sirf active areas, shehar ke hisab se."""
        out = {}
        for a in cls.objects.filter(is_active=True).order_by('city', 'sort_order', 'name'):
            out.setdefault(a.city, []).append(a)
        return list(out.items())

    @classmethod
    def valid_labels(cls):
        return {a.label for a in cls.objects.filter(is_active=True)}


class VendorProfile(models.Model):
    """Portal account of a Vendor. Customer side ke CustomerProfile jaisa."""
    vendor = models.OneToOneField(
        'Vendor', on_delete=models.CASCADE, related_name='portal_profile'
    )
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='vendor_profile'
    )
    business_name = models.CharField(max_length=100)
    city = models.CharField(max_length=100, blank=True, default='')
    is_approved = models.BooleanField(
        default=False,
        verbose_name="Approved",
        help_text="Approved vendor hi products list kar sakta hai"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Commission %",
        help_text="Shop is vendor ki har bikri par itna % rakhta hai. Khali = default "
                  "(settings.VENDOR_DEFAULT_COMMISSION_PERCENT, warna 10%)"
    )
    commission_promo_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Promo commission %",
        help_text="Launch offer: promo ki muddat me shop itna % rakhta hai (0 = commission-free). "
                  "Sirf tab lagta hai jab normal commission se kam ho aur 'Promo till' ki date na guzri ho."
    )
    commission_promo_until = models.DateField(
        null=True, blank=True, verbose_name="Promo till",
        help_text="Is date tak (is din samet) promo commission lagta hai. Date guzarne par normal rate "
                  "wapas aata hai (python manage.py expire_commission_promos roz chalayen)."
    )
    launch_promo_granted_at = models.DateTimeField(
        null=True, blank=True, editable=False,
        help_text="Naye vendor ka launch offer ek hi dafa milta hai; ye us ka nishan hai."
    )
    last_login_at = models.DateTimeField(null=True, blank=True)
    # Register ke waqt ka device hash (IP + browser) - blacklist ke liye
    signup_device = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    # ---- Payout account (vendor payout request ke liye, ek dafa save hota hai) ----
    PAYOUT_METHODS = [('bank', 'Bank Transfer'), ('jazzcash', 'JazzCash'), ('easypaisa', 'EasyPaisa')]
    payout_method = models.CharField(max_length=12, choices=PAYOUT_METHODS, blank=True, default='')
    payout_account_title = models.CharField(max_length=100, blank=True, default='',
                                            help_text="Account holder ka naam")
    payout_account_no = models.CharField(max_length=50, blank=True, default='',
                                         help_text="IBAN / account number / mobile account number")
    cuisines = models.ManyToManyField(
        'Cuisine', blank=True, related_name='stores',
        help_text="Is store ka khana (zyada se zyada 3). Customer stores page par cuisine se filter karta hai.")
    store_category = models.ForeignKey(
        'StoreCategory', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='stores', verbose_name="Store category",
        help_text="Store ki type (Restaurant, Grocery...). Customer stores isi se filter karta hai."
    )

    # ---- Store page (Talabat jaisi shop ki apni page) ----
    STORE_STATUS = [('open', 'Open'), ('busy', 'Busy'), ('closed', 'Closed')]
    store_description = models.TextField(blank=True, default='', max_length=1000)
    logo = models.ImageField(upload_to='vendor_stores/logos/', null=True, blank=True)
    cover_image = models.ImageField(upload_to='vendor_stores/covers/', null=True, blank=True)
    store_status = models.CharField(
        max_length=6, choices=STORE_STATUS, default='open',
        help_text="Closed = customer is store se order nahi de sakta. Busy = order milte hain, par der ho sakti ha."
    )
    hide_sold_out = models.BooleanField(
        default=False, verbose_name="Hide sold-out products",
        help_text="ON = stock 0 hote hi maal customer ko dikhna band (store page / shop home); restock par khud wapas aa jata hai.")
    low_stock_level = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Low-stock alert level",
        help_text="Is store ke maal par itne ya kam bachne par 'Low stock' alert. Khali = shop ki default hadd.")
    auto_accept = models.BooleanField(
        default=False, verbose_name="Auto-accept orders",
        help_text="ON = naya order aate hi khud qubool ho jata hai (ringtone nahi bajti). Customer ko ETA mil jati hai.")
    auto_accept_prep_minutes = models.PositiveSmallIntegerField(
        default=20, verbose_name="Auto-accept prep time (min)",
        help_text="Auto-accept par customer ko itne minute mein tayyar hone ka ETA dikhta hai.")
    paused_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Busy mode: is waqt tak naye orders band (khud khul jata hai). Khali = pause nahi."
    )
    opens_at = models.TimeField(null=True, blank=True, help_text="Khali = hamesha khula (status ke mutabiq)")
    closes_at = models.TimeField(null=True, blank=True)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fee_per_km = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, verbose_name="Fee per km",
        help_text="Free distance ke baad har extra km par itni fee. 0 = distance fee band (sirf upar wali fixed fee).")
    free_radius_km = models.DecimalField(
        max_digits=5, decimal_places=1, default=0, verbose_name="Free radius (km)",
        help_text="Itne km tak sirf base delivery fee lagti hai.")
    max_delivery_km = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Max delivery distance (km)",
        help_text="Is se door customer ko deliver nahi hota. Khali = koi had nahi.")
    delivery_time_min = models.PositiveSmallIntegerField(default=30, help_text="Minutes")
    delivery_time_max = models.PositiveSmallIntegerField(default=45, help_text="Minutes")
    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    # Branch: parent khali = main store; parent bhara = us owner ki branch (alag store, alag products/orders)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='branches',
        help_text="Khali = main store. Bhara = ye is store ki branch hai."
    )
    branch_name = models.CharField(max_length=60, blank=True, default='')
    delivery_areas = models.TextField(
        blank=True, default='', max_length=1000,
        help_text="Wo shehar/area jahan ye store deliver karta hai, comma se alag (jaise: Gulberg, DHA, Johar Town). "
                  "Khali = sirf store ke shehar mein."
    )

    class Meta:
        verbose_name_plural = '3.2 Vendor Portal Accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business_name} ({'approved' if self.is_approved else 'pending'})"

    MAX_AREAS = 50
    MAX_AREA_LEN = 60

    @classmethod
    def clean_areas(cls, text):
        """'Gulberg,  dha\nGulberg' -> ['Gulberg', 'dha'] (khali/dohraye hue hata kar, lambai/ginti ki had ke saath)."""
        import re
        seen, out = set(), []
        for part in re.split(r'[,\n;]+', text or ''):
            name = ' '.join(part.split())[:cls.MAX_AREA_LEN]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out[:cls.MAX_AREAS]

    @property
    def delivery_area_list(self):
        return self.clean_areas(self.delivery_areas)

    # ---- Timings: har din ka alag waqt (VendorDayHours), warna opens_at/closes_at roz ke liye ----
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def _day_map(self):
        cache = getattr(self, '_day_hours_cache', None)
        if cache is None:
            cache = {r.weekday: r for r in self.day_hours.all()}     # prefetch ho to koi extra query nahi
            self._day_hours_cache = cache
        return cache

    def hours_for_day(self, weekday):
        """-> 'closed' (us din band) | (opens, closes) | None (koi waqt tay nahi = khula)."""
        row = self._day_map().get(weekday)
        if row is not None:
            if row.is_closed:
                return 'closed'
            if row.opens_at and row.closes_at:
                return (row.opens_at, row.closes_at)
        if self.opens_at and self.closes_at:
            return (self.opens_at, self.closes_at)
        return None

    def within_hours_at(self, local_dt):
        """local_dt (aware, local time) par store ke waqt ke andar? Raat paar hone wale waqt
        (18:00 -> 02:00) agle din ke shuru ke ghanton ko bhi dhakte hain."""
        wd, t = local_dt.weekday(), local_dt.time()
        prev = self.hours_for_day((wd - 1) % 7)
        if isinstance(prev, tuple) and prev[0] > prev[1] and t <= prev[1]:
            return True
        today = self.hours_for_day(wd)
        if today is None:
            return True
        if today == 'closed':
            return False
        o, c = today
        if o <= c:
            return o <= t <= c
        return t >= o

    @staticmethod
    def _fmt_hours(h):
        if h == 'closed':
            return 'Closed'
        if h is None:
            return 'Open all day'
        return f"{h[0].strftime('%H:%M')} - {h[1].strftime('%H:%M')}"

    def hours_text_for(self, local_dt):
        return self._fmt_hours(self.hours_for_day(local_dt.weekday()))

    @property
    def has_day_hours(self):
        return bool(self._day_map())

    @property
    def has_any_hours(self):
        return bool(self._day_map()) or bool(self.opens_at and self.closes_at)

    @property
    def today_hours_text(self):
        return self.hours_text_for(timezone.localtime())

    @property
    def week_hours(self):
        today = timezone.localtime().weekday()
        return [{'day': self.DAY_NAMES[i], 'text': self._fmt_hours(self.hours_for_day(i)), 'today': i == today}
                for i in range(7)]

    @property
    def is_within_hours(self):
        """Opening/closing time ke andar? (din ke hisab se, raat paar hone wale time bhi theek)"""
        return self.within_hours_at(timezone.localtime())

    @property
    def is_open_now(self):
        """Customer abhi order de sakta ha?"""
        return (self.is_approved and self.store_status != 'closed' and self.is_within_hours
                and not self.is_paused)

    @property
    def is_paused(self):
        """Vendor ne 'Busy mode' laga rakha hai (naye orders temporarily band)?"""
        return bool(self.paused_until and self.paused_until > timezone.now())

    @property
    def paused_until_text(self):
        """Customer ko dikhane ke liye: 'orders 3:40 PM par dobara shuru'."""
        if not self.is_paused:
            return ''
        return timezone.localtime(self.paused_until).strftime('%I:%M %p').lstrip('0')

    @property
    def status_label(self):
        if not self.is_open_now:
            return 'closed'
        return 'busy' if self.store_status == 'busy' else 'open'



class VendorSubmission(Product):
    """Proxy: admin ke liye vendors ke jama kiye hue products ki alag list."""

    class Meta:
        proxy = True
        verbose_name = 'Vendor Product Submission'
        verbose_name_plural = '3.3 Vendor Product Submissions'


class VendorPayout(models.Model):
    """Marketplace vendor ko shop ki taraf se ada ki hui raqam (vendor ke hissay ki payment).
    Vendor ki bikri ka hissa `vendor_commission.vendor_earnings` nikalta hai; yahan wo paise
    record hote hain jo shop vendor ko de chuka. Baqi = payable - paid."""
    METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('jazzcash', 'JazzCash'),
        ('easypaisa', 'EasyPaisa'),
        ('cheque', 'Cheque'),
    ]
    vendor = models.ForeignKey('Vendor', on_delete=models.PROTECT, related_name='marketplace_payouts')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    method = models.CharField(max_length=12, choices=METHODS, default='bank')
    reference_no = models.CharField(max_length=100, blank=True, default='',
                                    help_text="Transaction ID / cheque number")
    notes = models.TextField(blank=True, default='')
    paid_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Vendor Payout'
        verbose_name_plural = '3.4 Vendor Payouts'
        ordering = ['-paid_at', '-id']
        indexes = [models.Index(fields=['vendor', 'paid_at'], name='app_vendorp_vendor_idx')]

    def __str__(self):
        return f"{self.vendor} - Rs. {self.amount} - {self.paid_at:%d-%m-%Y}"


class VendorPayoutRequest(models.Model):
    """Vendor ki taraf se 'mujhe meri raqam do' ki darkhwast.
    Raqam tab hi vendor ke hisab me 'paid' hoti hai jab admin request ko Paid mark kare
    (is waqt ek VendorPayout ban kar yahan link hota hai). Ek vendor ki ek waqt me sirf ek pending request."""
    STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled by vendor'),
    ]
    vendor = models.ForeignKey('Vendor', on_delete=models.PROTECT, related_name='payout_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    method = models.CharField(max_length=12, choices=VendorProfile.PAYOUT_METHODS, default='bank')
    account_title = models.CharField(max_length=100, blank=True, default='')
    account_no = models.CharField(max_length=50, blank=True, default='')
    note = models.CharField(max_length=200, blank=True, default='', help_text="Vendor ka paigham")
    status = models.CharField(max_length=10, choices=STATUS, default='pending', db_index=True)
    reject_reason = models.CharField(max_length=200, blank=True, default='')
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    payout = models.OneToOneField('VendorPayout', null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='request')

    class Meta:
        verbose_name = 'Vendor Payout Request'
        verbose_name_plural = '3.5 Vendor Payout Requests'
        ordering = ['-requested_at', '-id']
        constraints = [
            # Database level par: ek vendor ki sirf ek pending request (double-click / race se bachav)
            models.UniqueConstraint(fields=['vendor'], condition=models.Q(status='pending'),
                                    name='one_pending_payout_request_per_vendor'),
        ]

    def __str__(self):
        return f"{self.vendor} - Rs. {self.amount} - {self.get_status_display()}"


class StoreMenuSection(models.Model):
    """Store page par menu ke sections (categories) ki tarteeb - vendor khud tay karta hai.
    Jis category ki row na ho wo aakhir mein, naam ki tarteeb se aati hai."""
    store = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='menu_sections')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='+')
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Chhota number pehle nazar aata hai")

    class Meta:
        unique_together = ('store', 'category')
        ordering = ['sort_order', 'id']
        verbose_name = 'Store Menu Section'
        verbose_name_plural = 'Store Menu Sections'

    def __str__(self):
        return f"{self.store.business_name}: {self.category.name} ({self.sort_order})"


class StoreSponsorship(models.Model):
    """Sponsored / Featured store: vendor paise de kar store list aur homepage par upar aaye.
    Vendor request bhejta hai (pending), payment milne par admin Activate karta hai (Pro jaisa)."""
    STATUS_CHOICES = [
        ('pending', 'Pending (payment ka intezar)'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
    ]

    profile = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='sponsorships')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True, help_text="Is din tak (wo din samet) store upar rahega")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                 help_text="Vendor se li gayi raqam (aap ki income ka record)")
    note = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Store Sponsorship'
        verbose_name_plural = 'Store Sponsorships'

    def __str__(self):
        return f"{self.profile_id} sponsored ({self.status})"

    @property
    def is_running(self):
        return self.status == 'active' and bool(self.ends_on) and self.ends_on >= timezone.localdate()

    def activate(self, days):
        """Aaj se `days` din ke liye chalu karo (is store ki pehle se chalti sponsorship ho to us ke baad se)."""
        from datetime import timedelta
        today = timezone.localdate()
        base = today
        running = (StoreSponsorship.objects.filter(profile=self.profile, status='active', ends_on__gte=today)
                   .exclude(pk=self.pk).order_by('-ends_on').first())
        if running:
            base = running.ends_on + timedelta(days=1)
        self.starts_on = base
        self.ends_on = base + timedelta(days=max(int(days), 1) - 1)
        self.status = 'active'
        self.save()



class StoreDeal(models.Model):
    """Vendor ki apni deal: Buy 1 Get 1, Combo, ya Flash sale. Cart / checkout mein discount ki tarah lagti hai;
    discount vendor ke hisaab se katta hai (vendor ki payable mein se)."""
    KIND_CHOICES = [
        ('bogo', 'Buy 1 Get 1 Free'),
        ('combo', 'Combo deal'),
        ('flash', 'Flash sale'),
    ]

    profile = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='deals')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    title = models.CharField(max_length=80)
    percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                  help_text="Flash sale: kitne percent discount")
    combo_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                      help_text="Combo: poore set ki qeemat")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True, help_text="Khali = jab tak vendor khud band na kare")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Store Deal'
        verbose_name_plural = 'Store Deals'

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    def is_running(self, now=None):
        now = now or timezone.now()
        return bool(self.is_active and self.starts_at <= now and (self.ends_at is None or self.ends_at >= now))


class StoreDealItem(models.Model):
    """Deal mein shamil product (aur combo mein uski miqdar)."""
    deal = models.ForeignKey('StoreDeal', on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='deal_items')
    qty = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = 'Store Deal Item'
        verbose_name_plural = 'Store Deal Items'

    def __str__(self):
        return f"{self.qty} x {self.product_id}"


class OrderDeal(models.Model):
    """Order par kaun si deal lagi aur kitna discount mila (vendor ki payable se kati hui raqam ka record)."""
    order = models.ForeignKey('SaleOrder', on_delete=models.CASCADE, related_name='deals_applied')
    deal = models.ForeignKey('StoreDeal', on_delete=models.SET_NULL, null=True, blank=True, related_name='uses')
    vendor = models.ForeignKey('Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='deal_discounts')
    title = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Order Deal'
        verbose_name_plural = 'Order Deals'

    def __str__(self):
        return f"{self.order_id}: {self.title} -{self.amount}"


class VendorStaff(models.Model):
    """Store ka staff login (manager / orders-only). Owner ke VendorProfile ke neeche."""
    ROLE_MANAGER = 'manager'
    ROLE_ORDERS = 'orders'
    ROLE_CHOICES = [
        (ROLE_MANAGER, 'Manager (products, offers, reports, orders)'),
        (ROLE_ORDERS, 'Orders only (orders, busy mode)'),
    ]

    store = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='staff_members')
    extra_stores = models.ManyToManyField(
        'VendorProfile', blank=True, related_name='extra_staff',
        help_text="Staff in branches par bhi kaam karta hai (orders, notifications, switch)")
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='vendor_staff')
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20, unique=True, db_index=True,
                             help_text="Staff isi phone se login karta hai")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_ORDERS)
    is_active = models.BooleanField(default=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_active', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_role_display()}) - {self.store.business_name}"


class VendorDayHours(models.Model):
    """Kisi ek din (weekday) ka alag waqt. Row na ho to store ke roz wale opens_at/closes_at chalte hain."""
    store = models.ForeignKey('VendorProfile', on_delete=models.CASCADE, related_name='day_hours')
    weekday = models.PositiveSmallIntegerField(help_text="0 = Monday ... 6 = Sunday")
    is_closed = models.BooleanField(default=False, help_text="Is din store band")
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ('store', 'weekday')
        ordering = ['weekday']

    def __str__(self):
        return f"{self.store.business_name} - day {self.weekday}"
