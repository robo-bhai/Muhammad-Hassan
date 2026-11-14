"""Frontend views: purchase/vendor_documents - admin vendor ke documents review karta hai (approve / reject)."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import now

from ...customer import vendor_docs
from ...customer.store_orders import _notify as _vd_notify
from ...models import CompanyInfo, VendorDocument, VendorProfile
from ...security.permissions import perm_required


@login_required
@perm_required('view_vendors', post='edit_vendors')
def vendor_documents_review(request, pk):
    store = get_object_or_404(VendorProfile.objects.select_related('vendor', 'user'), pk=pk, parent__isnull=True)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        doc = get_object_or_404(VendorDocument, pk=request.POST.get('doc_id') or 0, store=store)
        label = vendor_docs.KIND_LABELS.get(doc.kind, doc.kind)
        if action == 'doc_approve':
            doc.status, doc.reject_reason = 'approved', ''
            _vd_notify(store.user, f'✅ {label} approved', 'Your document has been approved.',
                       '/shop/vendor/documents/', 'success')
        elif action == 'doc_reject':
            reason = (request.POST.get('reason') or '').strip()[:200]
            if not reason:
                messages.error(request, '❌ Please write the reason for rejecting.')
                return redirect('vendor_documents_review', pk=store.pk)
            doc.status, doc.reject_reason = 'rejected', reason
            _vd_notify(store.user, f'❌ {label} rejected', f'Reason: {reason}. Please upload it again.',
                       '/shop/vendor/documents/', 'warning')
        else:
            messages.error(request, '❌ Invalid action')
            return redirect('vendor_documents_review', pk=store.pk)
        doc.reviewed_by, doc.reviewed_at = request.user, now()
        doc.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at'])
        messages.success(request, f'{label}: {doc.get_status_display()}')
        return redirect('vendor_documents_review', pk=store.pk)

    today = timezone.localdate()
    docs = {d.kind: d for d in store.documents.all()}
    items = [{'kind': k, 'label': label, 'required': req, 'doc': docs.get(k),
              'expired': bool(docs.get(k) and docs[k].expiry and docs[k].expiry < today)}
             for k, label, _e, _n, req in vendor_docs.KINDS]
    ev = vendor_docs.evaluate([{'kind': d.kind, 'status': d.status, 'expiry': d.expiry} for d in docs.values()], today)
    return render(request, 'vendors/documents_review.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'store': store, 'items': items, 'ev': ev, 'summary': vendor_docs.summary(ev),
    })
