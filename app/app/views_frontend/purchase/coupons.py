"""Frontend views: purchase/coupons

Promo codes / store offers ab seedha app se manage hote hain (banners jaisa):
  - List    : status (Live / Scheduled / Expired / Used up / Off), kitni dafa use hua, on/off, edit, delete
  - Add/Edit: percent ya fixed, min order, store (optional), dates, limits

Permissions: dekhna = view_vendors, badalna = edit_vendors (banners wali).
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ...models import CompanyInfo, Coupon, VendorProfile
from ...security.permissions import perm_required

LIST_URL = '/vendors/coupons/'


def _company_name():
    c = CompanyInfo.objects.first()
    return c.name if c else 'ERP System'


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ['code', 'title', 'discount_type', 'value', 'max_discount', 'min_order', 'store',
                  'show_on_store', 'first_order_only', 'usage_limit', 'per_customer_limit',
                  'starts_on', 'ends_on', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control text-uppercase', 'maxlength': 30,
                                           'placeholder': 'WELCOME20', 'autocomplete': 'off'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 80, 'placeholder': '20% off'}),
            'discount_type': forms.Select(attrs={'class': 'form-select'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'max_discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'min_order': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'store': forms.Select(attrs={'class': 'form-select'}),
            'show_on_store': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'first_order_only': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'usage_limit': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'per_customer_limit': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'starts_on': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'ends_on': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['store'].queryset = VendorProfile.objects.filter(is_approved=True).order_by('business_name')
        self.fields['store'].empty_label = '— Har store (sab par) —'

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper().replace(' ', '')
        if len(code) < 3:
            raise forms.ValidationError('Code kam az kam 3 harf/ginti ka ho.')
        if not code.isalnum():
            raise forms.ValidationError('Code mein sirf harf aur ginti (A-Z, 0-9) allowed hain.')
        clash = Coupon.objects.filter(code=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('Yeh code pehle se maujood hai.')
        return code

    def clean(self):
        data = super().clean()
        typ, val = data.get('discount_type'), data.get('value')
        if val is not None:
            if val <= 0:
                self.add_error('value', 'Value 0 se zyada honi chahiye.')
            elif typ == Coupon.TYPE_PERCENT and val > 100:
                self.add_error('value', 'Percent 100 se zyada nahi ho sakta.')
        if typ == Coupon.TYPE_FIXED:
            data['max_discount'] = None
        start, end = data.get('starts_on'), data.get('ends_on')
        if start and end and end < start:
            self.add_error('ends_on', 'End date start date se pehle nahi ho sakti.')
        if data.get('show_on_store') and not data.get('store'):
            data['show_on_store'] = False          # badge sirf store wale coupon ka
        return data


@login_required
@perm_required('view_vendors')
def coupon_list(request):
    coupons = list(Coupon.objects.select_related('store').annotate(
        n_used=Count('redemptions'), total_off=Sum('redemptions__amount')))
    counts = {'live': 0, 'scheduled': 0, 'expired': 0, 'used_up': 0, 'off': 0}
    for c in coupons:
        c.state = c.status
        counts[c.state] += 1
    return render(request, 'vendors/coupons.html', {
        'company_name': _company_name(), 'coupons': coupons, 'counts': counts, 'total': len(coupons),
    })


@login_required
@perm_required('view_vendors', post='edit_vendors')
def coupon_form(request, pk=None):
    coupon = get_object_or_404(Coupon, pk=pk) if pk else None
    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'✅ Coupon "{obj.code}" save ho gaya.')
            return redirect(LIST_URL)
        messages.error(request, '❌ Form mein ghaltiyan hain, neeche dekhein.')
    else:
        form = CouponForm(instance=coupon)
    return render(request, 'vendors/coupon_form.html', {
        'company_name': _company_name(), 'form': form, 'coupon': coupon,
    })


@login_required
@perm_required('edit_vendors')
@require_POST
def coupon_toggle(request, pk):
    c = get_object_or_404(Coupon, pk=pk)
    c.is_active = not c.is_active
    c.save(update_fields=['is_active'])
    messages.success(request, f'✅ "{c.code}" ' + ('ON kar diya.' if c.is_active else 'OFF kar diya.'))
    return redirect(LIST_URL)


@login_required
@perm_required('edit_vendors')
@require_POST
def coupon_delete(request, pk):
    c = get_object_or_404(Coupon, pk=pk)
    code, used = c.code, c.redemptions.count()
    if used:
        # istemal ho chuka coupon delete nahi karte (report/order ka record rahe) - sirf OFF
        c.is_active = False
        c.save(update_fields=['is_active'])
        messages.warning(request, f'"{code}" {used} order(s) par lag chuka hai, is liye delete nahi hua - OFF kar diya gaya.')
    else:
        c.delete()
        messages.warning(request, f'🗑️ Coupon "{code}" delete ho gaya.')
    return redirect(LIST_URL)
