"""Frontend views: blacklist (blocked phone / email / device) - dekhna, haath se add karna, hatana."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ...models import BlockedIdentity, CompanyInfo
from ...security.permissions import perm_required
from ...utils.account_log import log_action
from ...utils.blacklist import block_identity

_log = logging.getLogger(__name__)


@login_required
@perm_required('edit_customers')
def blocked_list(request):
    qs = BlockedIdentity.objects.filter(is_active=True).select_related('created_by')
    search = request.GET.get('search', '').strip()
    kind = request.GET.get('kind', '')
    if search:
        qs = qs.filter(Q(label__icontains=search) | Q(reason__icontains=search))
    if kind in ('phone', 'email', 'device'):
        qs = qs.filter(kind=kind)
    page_obj = Paginator(qs, 30).get_page(request.GET.get('page', 1))
    return render(request, 'blocked/list.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj, 'search': search, 'kind': kind,
        'total': BlockedIdentity.objects.filter(is_active=True).count(),
    })


@login_required
@perm_required('edit_customers')
@require_POST
def blocked_add(request):
    kind = request.POST.get('kind', '')
    value = request.POST.get('value', '').strip()
    reason = request.POST.get('reason', '').strip()[:255]
    if kind not in ('phone', 'email'):          # device sirf suspend ke saath (uska hash haath se nahi likha jata)
        messages.error(request, '❌ Sirf phone ya email haath se add ho sakta hai.')
    elif not block_identity(kind, value, reason=reason, source='manual', user=request.user):
        messages.error(request, '❌ Phone ya email theek likhein (phone kam az kam 8 digits, email mein @).')
    else:
        _log.warning('Blacklist add %s=%s by %s', kind, value, request.user)
        log_action('other', None, value, 'block', reason=reason, detail=kind, user=request.user)
        messages.success(request, f'🚫 "{value}" blacklist ho gaya. Is se naya account nahi ban sakega.')
    return redirect('blocked_list')


@login_required
@perm_required('edit_customers')
@require_POST
def blocked_remove(request, pk):
    entry = get_object_or_404(BlockedIdentity, pk=pk)
    label = entry.label or entry.value
    entry.delete()
    _log.warning('Blacklist remove %s by %s', label, request.user)
    log_action('other', None, label, 'unblock', detail=entry.kind, user=request.user)
    messages.success(request, f'✅ "{label}" blacklist se hat gaya.')
    return redirect('blocked_list')
