"""Frontend views: duplicate customers / vendors report (sirf dikhata hai, kuch badalta ya merge nahi karta)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ...models import CompanyInfo, Customer, Vendor
from ...security.permissions import perm_required
from ...utils.phone_utils import group_duplicates, is_comparable, phone_key


def _phone_key(row):
    raw = row['contact_number']
    return phone_key(raw) if is_comparable(raw) else ''


@login_required
@perm_required('view_customers')
def duplicate_report(request):
    """Ek hi phone / email / naam par kai customers ya vendors - ek jagah list."""
    customers = list(Customer.objects.values('id', 'name', 'customer_code', 'contact_number', 'email'))
    vendors = list(Vendor.objects.values('id', 'name', 'vendor_code', 'contact_number'))

    cust_phone = group_duplicates(customers, _phone_key)
    cust_email = group_duplicates(customers, lambda r: (r['email'] or '').strip().lower())
    vend_phone = group_duplicates(vendors, _phone_key)
    vend_name = group_duplicates(vendors, lambda r: ' '.join((r['name'] or '').lower().split()))

    # Ek hi number customer aur vendor dono par (ho sakta hai asli mein ek hi shakhs ho - sirf maloomat)
    by_key_c, by_key_v = {}, {}
    for r in customers:
        k = _phone_key(r)
        if k:
            by_key_c.setdefault(k, []).append(r)
    for r in vendors:
        k = _phone_key(r)
        if k:
            by_key_v.setdefault(k, []).append(r)
    both = [{'key': k, 'customers': by_key_c[k], 'vendors': by_key_v[k]}
            for k in sorted(set(by_key_c) & set(by_key_v))]

    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'cust_phone': cust_phone,
        'cust_email': cust_email,
        'vend_phone': vend_phone,
        'vend_name': vend_name,
        'both': both,
        'total_groups': len(cust_phone) + len(cust_email) + len(vend_phone) + len(vend_name),
        'customer_count': len(customers),
        'vendor_count': len(vendors),
    }
    return render(request, 'duplicates/report.html', context)
