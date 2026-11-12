"""Admin: vendor portal (vendor accounts + vendor product approvals)."""
from ..models import *
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.timezone import now


@admin.register(StoreCategory, site=admin.site)
class StoreCategoryAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'sort_order', 'is_active', 'store_count')
    list_display_links = ('icon', 'name')
    list_editable = ('sort_order', 'is_active')
    search_fields = ('name',)

    @admin.display(description='Stores')
    def store_count(self, obj):
        return obj.stores.count()


@admin.register(Cuisine, site=admin.site)
class CuisineAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'sort_order', 'is_active', 'store_count')
    list_display_links = ('icon', 'name')
    list_editable = ('sort_order', 'is_active')
    search_fields = ('name',)

    @admin.display(description='Stores')
    def store_count(self, obj):
        return obj.stores.count()


@admin.register(DeliveryArea, site=admin.site)
class DeliveryAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'extra_fee', 'sort_order', 'is_active')
    list_editable = ('extra_fee', 'sort_order', 'is_active')
    list_filter = ('city', 'is_active')
    search_fields = ('name', 'city')
    actions = ['bulk_note']

    @admin.action(description='Tip: ek saath bohat areas ke liye "Add" mein ek ek karke ya shell se import karein')
    def bulk_note(self, request, queryset):
        messages.info(request, 'Bulk import ke liye: python manage.py import_areas file.csv (city,area)')


@admin.register(VendorProfile, site=admin.site)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'vendor', 'user', 'city', 'store_category', 'is_approved', 'store_status', 'created_at', 'last_login_at')
    list_filter = ('is_approved', 'store_status', 'store_category', 'cuisines', 'city')
    filter_horizontal = ('cuisines',)
    search_fields = ('business_name', 'vendor__name', 'vendor__contact_number', 'user__email')
    readonly_fields = ('vendor', 'user', 'approved_at', 'last_login_at', 'created_at')
    actions = ['approve_accounts', 'suspend_accounts']

    PROMO_FIELDS = {'commission_percent', 'commission_promo_percent', 'commission_promo_until'}

    @admin.action(description='Approve selected vendors')
    def approve_accounts(self, request, queryset):
        from ..customer.vendor_commission import on_vendor_approved
        pending = queryset.filter(is_approved=False)
        first_time = list(pending.filter(approved_at__isnull=True))   # pehli approval: launch offer ke qabil
        n = pending.update(is_approved=True, approved_at=now())
        promos = sum(1 for p in first_time if on_vendor_approved(p, first_time=True))
        msg = f'{n} vendor(s) approved.'
        if promos:
            msg += f' {promos} ko launch commission offer mila.'
        self.message_user(request, msg, messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Commission ya promo badla: batch ka cost naye rate par (commission batch me bake hota hai)
        if change and self.PROMO_FIELDS & set(form.changed_data):
            from ..customer.vendor_commission import commission_percent, reprice_vendor_batches
            failed = reprice_vendor_batches(obj)
            self.message_user(request, f'Commission ab {commission_percent(obj)}% hai; open batches update ho gaye.',
                              messages.SUCCESS)
            if failed:
                self.message_user(request, 'In products ka cost update nahi ho saka (margin policy): '
                                  + ' | '.join(failed[:5]), messages.WARNING)

    @admin.action(description='Suspend selected vendors (aur unke products shop se hatao)')
    def suspend_accounts(self, request, queryset):
        vendor_ids = list(queryset.values_list('vendor_id', flat=True))
        queryset.update(is_approved=False)
        hidden = Product.objects.filter(vendor_id__in=vendor_ids).update(is_active=False)
        self.message_user(
            request, f'{len(vendor_ids)} vendor(s) suspended, {hidden} product(s) hidden.',
            messages.WARNING
        )


@admin.register(VendorSubmission, site=admin.site)
class VendorSubmissionAdmin(admin.ModelAdmin):
    """Vendors ke products: review, approve ya reject."""
    list_display = ('name', 'vendor', 'category', 'price', 'approval_status', 'is_active', 'created_at')
    list_filter = ('approval_status', 'vendor', 'category')
    search_fields = ('name', 'vendor__name', 'barcode')
    actions = ['approve_products', 'reject_products']
    fields = ('name', 'description', 'vendor', 'category', 'brand', 'unit', 'image',
              'original_price', 'discount_percentage', 'price', 'approval_status',
              'rejection_reason', 'is_active')
    # Sirf approval wale fields badal sakte hain (image dobara process na ho).
    readonly_fields = ('name', 'description', 'vendor', 'category', 'brand', 'unit', 'image',
                       'original_price', 'discount_percentage', 'price', 'is_active')

    def get_queryset(self, request):
        return super().get_queryset(request).filter(vendor__isnull=False).select_related('vendor', 'category')

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        obj._image_processed = True  # Product.save() ka image API call skip
        if obj.approval_status == 'approved':
            if 'approval_status' in form.changed_data:
                obj.is_active = True
            obj.rejection_reason = ''
        else:
            obj.is_active = False
        super().save_model(request, obj, form, change)

    @admin.action(description='Approve selected products (shop par live karo)')
    def approve_products(self, request, queryset):
        n = queryset.exclude(approval_status='approved').update(
            approval_status='approved', is_active=True, rejection_reason='')
        self.message_user(request, f'{n} product(s) approved aur shop par live.', messages.SUCCESS)

    @admin.action(description='Reject selected products')
    def reject_products(self, request, queryset):
        n = queryset.update(
            approval_status='rejected', is_active=False,
            rejection_reason='Listing guidelines par poora nahi utarta. Edit karke dobara bhejein.')
        self.message_user(request, f'{n} product(s) rejected.', messages.WARNING)


@admin.register(ShopBanner, site=admin.site)
class ShopBannerAdmin(admin.ModelAdmin):
    """Stores page ke upar wale promo banners: upload, order, on/off, date range."""
    list_display = ('preview', 'title', 'store', 'is_active', 'sort_order', 'starts_on', 'ends_on')
    list_display_links = ('preview', 'title')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active', 'store')
    search_fields = ('title', 'store__business_name')
    fields = ('title', 'image', 'store', 'link_url', 'is_active', 'sort_order', 'starts_on', 'ends_on')

    @admin.display(description='Banner')
    def preview(self, obj):
        if not obj.image:
            return '-'
        return format_html('<img src="{}" style="height:48px;border-radius:6px;">', obj.image.url)


class VendorPayoutForm(forms.ModelForm):
    class Meta:
        model = VendorPayout
        fields = ('vendor', 'amount', 'method', 'reference_no', 'notes', 'paid_at')

    def clean(self):
        from decimal import Decimal
        from ..vendor_commission import vendor_earnings
        data = super().clean()
        vendor, amount = data.get('vendor'), data.get('amount')
        if vendor and amount is not None:
            if amount <= 0:
                raise forms.ValidationError('Amount zero se zyada honi chahiye.')
            if not hasattr(vendor, 'portal_profile'):
                raise forms.ValidationError('Ye vendor marketplace (portal) vendor nahi hai.')
            balance = vendor_earnings(vendor)['balance']
            if amount > balance:
                raise forms.ValidationError(
                    f'Amount baqi raqam se zyada hai. Is vendor ka baqi: Rs. {balance:,.2f}')
        return data


@admin.register(VendorPayout, site=admin.site)
class VendorPayoutAdmin(admin.ModelAdmin):
    """Vendor ko kiye gaye payments. Sirf add/dekhna; ghalti ho to naya entry (hazf nahi)."""
    form = VendorPayoutForm
    list_display = ('paid_at', 'vendor', 'amount', 'method', 'reference_no', 'created_by', 'vendor_balance')
    list_filter = ('method', 'vendor')
    search_fields = ('vendor__name', 'reference_no', 'notes')
    date_hierarchy = 'paid_at'
    autocomplete_fields = ()
    readonly_fields = ('created_by', 'created_at')

    @admin.display(description='Baqi (abhi)')
    def vendor_balance(self, obj):
        from ..vendor_commission import vendor_earnings
        return f"Rs. {vendor_earnings(obj.vendor)['balance']:,.2f}"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('vendor', 'created_by')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)  # list dekh sakte hain, edit nahi

    def has_delete_permission(self, request, obj=None):
        return False


class VendorPayoutRequestForm(forms.ModelForm):
    """Admin ka faisla: Paid (reference ke sath) ya Reject (wajah ke sath). Baqi sab sirf dekhne ke liye."""
    decision = forms.ChoiceField(
        required=False, label='Faisla',
        choices=[('', '-- Pending rehne den --'), ('paid', 'Paid mark karen (paise bhej diye)'),
                 ('rejected', 'Reject karen')])
    reference_no = forms.CharField(
        required=False, max_length=100, label='Transaction ID / reference',
        help_text='Paid mark karne ke liye zaroori. Bank/JazzCash/EasyPaisa ki transaction ID.')

    class Meta:
        model = VendorPayoutRequest
        fields = ('reject_reason',)

    def clean(self):
        data = super().clean()
        decision = data.get('decision')
        if decision == 'paid' and not (data.get('reference_no') or '').strip():
            self.add_error('reference_no', 'Transaction ID / reference number likhna zaroori hai.')
        if decision == 'rejected' and not (data.get('reject_reason') or '').strip():
            self.add_error('reject_reason', 'Reject karne ki wajah likhen (vendor ko dikhai jaye gi).')
        return data


@admin.register(VendorPayoutRequest, site=admin.site)
class VendorPayoutRequestAdmin(admin.ModelAdmin):
    """Vendor ki payout requests. Paid mark karne par VendorPayout khud ban jata hai."""
    form = VendorPayoutRequestForm
    list_display = ('requested_at', 'vendor', 'amount', 'method', 'status', 'vendor_withdrawable', 'reviewed_by')
    list_filter = ('status', 'method')
    search_fields = ('vendor__name', 'account_title', 'account_no')
    date_hierarchy = 'requested_at'
    readonly_fields = ('vendor', 'amount', 'method', 'account_title', 'account_no', 'note', 'status',
                       'requested_at', 'reviewed_by', 'reviewed_at', 'payout', 'vendor_withdrawable')

    def get_fields(self, request, obj=None):
        base = ['vendor', 'amount', 'method', 'account_title', 'account_no', 'note', 'status',
                'requested_at', 'vendor_withdrawable']
        if obj is not None and obj.status == 'pending':
            return base + ['decision', 'reference_no', 'reject_reason']
        return base + ['reject_reason', 'reviewed_by', 'reviewed_at', 'payout']

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj is None or obj.status != 'pending':
            ro.append('reject_reason')
        return ro

    @admin.display(description='Vendor ka abhi nikalne ke qabil')
    def vendor_withdrawable(self, obj):
        from ..customer.payout_requests import withdrawable
        w = withdrawable(obj.vendor)
        return (f"Rs. {w['available']:,.2f} (baqi {w['balance']:,.2f}, ruki {w['held_recent']:,.2f}, "
                f"rider cash {w['held_cash']:,.2f})")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('vendor', 'reviewed_by')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        from ..customer import payout_requests
        decision = form.cleaned_data.get('decision')
        if not change or not decision:
            return
        try:
            if decision == 'paid':
                payout_requests.mark_paid(obj.pk, request.user, form.cleaned_data.get('reference_no'))
                self.message_user(request, f'Paid mark ho gayi: Rs. {obj.amount:,.2f} ({obj.vendor}).', messages.SUCCESS)
            else:
                payout_requests.reject(obj.pk, request.user, form.cleaned_data.get('reject_reason'))
                self.message_user(request, 'Request reject kar di gayi.', messages.SUCCESS)
        except payout_requests.PayoutError as exc:
            self.message_user(request, f'Nahi hua: {exc}', messages.ERROR)


@admin.register(StoreMenuSection, site=admin.site)
class StoreMenuSectionAdmin(admin.ModelAdmin):
    list_display = ('store', 'category', 'sort_order')
    list_filter = ('store',)
    ordering = ('store', 'sort_order')


@admin.register(FavoriteStore, site=admin.site)
class FavoriteStoreAdmin(admin.ModelAdmin):
    list_display = ('store', 'customer', 'created_at')
    list_filter = ('store',)
    raw_id_fields = ('customer', 'store')


@admin.register(WishlistItem, site=admin.site)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'customer', 'created_at')
    search_fields = ('product__name',)
    raw_id_fields = ('customer', 'product')


# ============================================
# OFFERS: Coupons, Wallet, Pro
# ============================================

class CouponRedemptionInline(admin.TabularInline):
    model = CouponRedemption
    extra = 0
    can_delete = False
    fields = ('order', 'customer', 'amount', 'created_at')
    readonly_fields = ('order', 'customer', 'amount', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Coupon, site=admin.site)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'discount_type', 'value', 'min_order', 'store', 'state', 'used', 'is_active')
    list_filter = ('is_active', 'discount_type', 'store')
    search_fields = ('code', 'title')
    raw_id_fields = ('store',)
    inlines = [CouponRedemptionInline]

    @admin.display(description='State')
    def state(self, obj):
        return obj.status

    @admin.display(description='Used')
    def used(self, obj):
        return obj.used_count


class WalletTransactionForm(forms.ModelForm):
    """Haath se sirf Top-up (shop ko cash mila) ya Adjustment; baqi (spend/refund/cashback) system banata hai."""

    class Meta:
        model = WalletTransaction
        fields = ('customer', 'kind', 'amount', 'note')

    def clean(self):
        from decimal import Decimal
        from ..customer import offers
        data = super().clean()
        kind, amount, customer = data.get('kind'), data.get('amount'), data.get('customer')
        if kind not in ('topup', 'adjust'):
            raise forms.ValidationError('Sirf Top-up ya Adjustment haath se ban sakta hai. Baqi system khud banata hai.')
        if amount is None or amount == 0:
            raise forms.ValidationError('Raqam 0 nahi ho sakti.')
        if kind == 'topup' and amount < 0:
            raise forms.ValidationError('Top-up ki raqam positive honi chahiye (katna ho to Adjustment use karein).')
        if customer and amount < 0 and offers.wallet_balance(customer) + Decimal(amount) < 0:
            raise forms.ValidationError('Customer ke balance se zyada nahi kat sakta.')
        return data


@admin.register(WalletTransaction, site=admin.site)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Wallet ka khata: nayi entry sirf Top-up / Adjustment; purani entry badli ya hatai nahi ja sakti."""
    form = WalletTransactionForm
    list_display = ('created_at', 'customer', 'kind', 'amount', 'order', 'note')
    list_filter = ('kind',)
    search_fields = ('customer__name', 'customer__contact_number', 'note')
    raw_id_fields = ('customer', 'order')
    date_hierarchy = 'created_at'

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('customer', 'kind', 'amount', 'order', 'note', 'created_by', 'created_at')
        return ()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Referral, site=admin.site)
class ReferralAdmin(admin.ModelAdmin):
    """Customer referrals. Reward system khud deta hai (referee ka pehla delivered order); yahan sirf dekhna aur
    haath se faisla: Approve (fraud checks ke baghair reward) ya Reject (pending ko band)."""
    list_display = ('created_at', 'referrer', 'referrer_phone', 'referee', 'referee_phone', 'status',
                    'referrer_amount', 'referee_amount', 'rewarded_at', 'reject_reason')
    list_filter = ('status', 'created_at')
    search_fields = ('referrer__name', 'referrer__contact_number', 'referee__name', 'referee__contact_number',
                     'referrer__portal_profile__referral_code', 'referee__portal_profile__referral_code')
    date_hierarchy = 'created_at'
    list_select_related = ('referrer', 'referee')
    readonly_fields = ('referrer', 'referee', 'status', 'reject_reason', 'device_hash', 'reward_order',
                       'referrer_amount', 'referee_amount', 'created_at', 'rewarded_at')
    actions = ['approve_selected', 'reject_selected']

    @admin.display(description='Referrer phone')
    def referrer_phone(self, obj):
        return obj.referrer.contact_number

    @admin.display(description='Referee phone')
    def referee_phone(self, obj):
        return obj.referee.contact_number

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='✅ Approve (reward do - fraud checks ke baghair)')
    def approve_selected(self, request, queryset):
        from ..customer.referrals import ReferralActionError, manual_approve
        done, errors = 0, []
        for pk in queryset.exclude(status='rewarded').values_list('pk', flat=True):
            try:
                manual_approve(pk)
                done += 1
            except ReferralActionError as exc:
                errors.append(f'#{pk}: {exc}')
        if done:
            self.message_user(request, f'{done} referral ka reward de diya gaya.', messages.SUCCESS)
        if errors:
            self.message_user(request, 'Nahi hua: ' + ' | '.join(errors[:5]), messages.WARNING)
        if not done and not errors:
            self.message_user(request, 'Chune hue sab referral ko reward pehle hi mil chuka hai.', messages.INFO)

    @admin.action(description='❌ Reject (sirf pending; reward ho chuka wapas nahi hota)')
    def reject_selected(self, request, queryset):
        n = queryset.filter(status='pending').update(status='rejected', reject_reason='Admin ne reject kiya')
        skipped = queryset.exclude(status='pending').count()
        self.message_user(request, f'{n} referral reject ho gaye.' + (f' {skipped} chhor diye (pending nahi the).' if skipped else ''),
                          messages.WARNING if n else messages.INFO)


@admin.register(ProMembership, site=admin.site)
class ProMembershipAdmin(admin.ModelAdmin):
    list_display = ('customer', 'status', 'requested_at', 'starts_on', 'ends_on', 'amount')
    list_filter = ('status',)
    search_fields = ('customer__name', 'customer__contact_number')
    raw_id_fields = ('customer',)
    actions = ['activate_selected', 'cancel_selected']

    @admin.action(description='✅ Activate (payment mil gayi) - Settings ki mudat ke liye')
    def activate_selected(self, request, queryset):
        from ..customer import offers
        cfg = offers.pro_settings()
        done = 0
        for m in queryset.exclude(status='active'):
            if not m.amount:
                m.amount = cfg['price']
            m.activate(cfg['days'])
            done += 1
        self.message_user(request, f'{done} membership activate ho gayi ({cfg["days"]} din).', messages.SUCCESS)

    @admin.action(description='❌ Cancel')
    def cancel_selected(self, request, queryset):
        n = queryset.update(status='cancelled')
        self.message_user(request, f'{n} membership cancel ho gayi.', messages.WARNING)


class LoyaltyAdjustForm(forms.ModelForm):
    """Haath se sirf Adjustment (points dena / katna); 'earn' aur 'redeem' system banata hai."""

    class Meta:
        model = LoyaltyTransaction
        fields = ('customer', 'points', 'note')

    def clean(self):
        from ..customer import offers
        data = super().clean()
        points, customer = data.get('points'), data.get('customer')
        if not points:
            raise forms.ValidationError('Points 0 nahi ho sakte.')
        if customer and points < 0 and offers.points_balance(customer) + points < 0:
            raise forms.ValidationError('Customer ke points se zyada nahi kat sakte.')
        return data


@admin.register(LoyaltyTransaction, site=admin.site)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    """Loyalty points ka khata: nayi entry sirf Adjustment; purani entry badli ya hatai nahi ja sakti."""
    form = LoyaltyAdjustForm
    list_display = ('created_at', 'customer', 'kind', 'points', 'order', 'note')
    list_filter = ('kind',)
    search_fields = ('customer__name', 'customer__contact_number', 'note')
    raw_id_fields = ('customer', 'order')
    date_hierarchy = 'created_at'

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('customer', 'points', 'kind', 'order', 'note', 'created_by', 'created_at')
        return ()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.kind = 'adjust'
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
