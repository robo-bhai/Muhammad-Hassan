"""Frontend views: suspend / unsuspend / approve / blacklist ki history (kis ne, kab, kyun)."""
import csv
from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render

from ...models import AccountActionLog, CompanyInfo, CustomerProfile, VendorProfile
from ...security.permissions import perm_required


def _date(raw):
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


@login_required
@perm_required('view_customers')
def account_history(request):
    kind = request.GET.get('kind', '')
    action = request.GET.get('action', '')
    search = request.GET.get('search', '').strip()
    d_from = _date(request.GET.get('from'))
    d_to = _date(request.GET.get('to'))

    qs = AccountActionLog.objects.all()
    if kind in ('customer', 'vendor', 'other'):
        qs = qs.filter(kind=kind)
    if action in dict(AccountActionLog.ACTION_CHOICES):
        qs = qs.filter(action=action)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(reason__icontains=search)
                       | Q(by_name__icontains=search) | Q(detail__icontains=search))
    if d_from:
        qs = qs.filter(created_at__date__gte=d_from)
    if d_to:
        qs = qs.filter(created_at__date__lte=d_to)

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="account_history.csv"'
        resp.write('\ufeff')                                   # Excel mein sahi khule
        w = csv.writer(resp)
        w.writerow(['Date', 'Type', 'Name', 'Action', 'Reason', 'Detail', 'Kis ne'])
        for r in qs.iterator():
            w.writerow([r.created_at.strftime('%Y-%m-%d %H:%M'), r.get_kind_display(), r.name,
                        r.get_action_display(), r.reason, r.detail, r.by_name])
        return resp

    keep = {k: v for k, v in (('kind', kind), ('action', action), ('search', search),
                              ('from', request.GET.get('from', '')), ('to', request.GET.get('to', ''))) if v}
    return render(request, 'account_history/list.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': Paginator(qs, 30).get_page(request.GET.get('page', 1)),
        'kind': kind, 'action': action, 'search': search,
        'd_from': request.GET.get('from', ''), 'd_to': request.GET.get('to', ''),
        'keep': urlencode(keep),
        'actions': AccountActionLog.ACTION_CHOICES,
        'suspended_customers': CustomerProfile.objects.filter(is_suspended=True).count(),
        'suspended_vendors': VendorProfile.objects.filter(is_approved=False, approved_at__isnull=False).count(),
        'total': AccountActionLog.objects.count(),
    })
