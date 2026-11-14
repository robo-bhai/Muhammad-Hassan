"""Vendor documents (CR, owner ID, bank proof, VAT, health licence) - Talabat Bahrain jaisa onboarding.

Vendor (sirf owner): /shop/vendor/documents/  (upload)     Admin review: /vendors/<id>/documents/
Documents sirf vendor_document_file ke zariye khulte hain (owner khud ya admin); URL kabhi seedha nahi diya jata.
"""
import mimetypes
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import vendor_login_required
from ..models import VendorDocument
from . import vendor_docs
from .vendor_access import get_vendor_profile
from .views_rider_onboarding import NUMBER_RE, _clean_doc_file, _parse_date


def legal_profile(profile):
    """Documents main store par lagte hain; branch ho to uska parent."""
    return profile.parent if getattr(profile, 'parent_id', None) else profile


def doc_eval(store):
    docs = [{'kind': d.kind, 'status': d.status, 'expiry': d.expiry} for d in store.documents.all()]
    return vendor_docs.evaluate(docs, timezone.localdate())


def doc_warnings(profile):
    """Vendor dashboard ke liye: [(level, text)]. Koi document upload na hua ho to khali (purane vendors tang na hon)."""
    store = legal_profile(profile)
    if not store.documents.exists():
        return []
    return vendor_docs.warnings(doc_eval(store))


def docs_complete(profile):
    return doc_eval(legal_profile(profile))['complete']


@vendor_login_required
def vendor_documents(request):
    store = legal_profile(get_vendor_profile(request.user))
    today = timezone.localdate()
    if request.method == 'POST':
        kind = request.POST.get('kind', '')
        label = vendor_docs.KIND_LABELS.get(kind)
        number = (request.POST.get('number') or '').strip()
        expiry = _parse_date(request.POST.get('expiry'))
        error = None
        if not label:
            error = 'Unknown document type.'
        elif kind in vendor_docs.NEEDS_NUMBER and not NUMBER_RE.match(number):
            error = f'{label}: enter the number (3-40 letters or digits).'
        elif kind in vendor_docs.NEEDS_EXPIRY and not expiry:
            error = f'{label}: choose the expiry date.'
        elif kind in vendor_docs.NEEDS_EXPIRY and expiry <= today:
            error = f'{label} has expired. Upload a valid document.'
        if not error:
            try:
                f = _clean_doc_file(request.FILES.get('file'))
            except ValueError as exc:
                error = str(exc)
        if error:
            messages.error(request, '❌ ' + error)
            return redirect('vendor_documents')
        fields = dict(number=number if kind in vendor_docs.NEEDS_NUMBER else '',
                      expiry=expiry if kind in vendor_docs.NEEDS_EXPIRY else None)
        with transaction.atomic():
            doc = VendorDocument.objects.select_for_update().filter(store=store, kind=kind).first()
            if doc:
                old = doc.file
                doc.file = f
                doc.number, doc.expiry = fields['number'], fields['expiry']
                doc.status, doc.reject_reason, doc.reviewed_by, doc.reviewed_at = 'pending', '', None, None
                doc.save()
                try:
                    old.storage.delete(old.name)      # purani file hata do (naya record save ho chuka)
                except Exception:
                    pass
            else:
                VendorDocument.objects.create(store=store, kind=kind, file=f, **fields)
        messages.success(request, f'✅ {label} uploaded. Our team will review it.')
        return redirect('vendor_documents')

    docs = {d.kind: d for d in store.documents.all()}
    soon = today + timedelta(days=vendor_docs.SOON_DAYS)
    items = []
    for kind, label, needs_exp, needs_num, required in vendor_docs.KINDS:
        d = docs.get(kind)
        items.append({'kind': kind, 'label': label, 'needs_exp': needs_exp, 'needs_num': needs_num,
                      'required': required, 'doc': d,
                      'expired': bool(d and d.expiry and d.expiry < today),
                      'expiring': bool(d and d.expiry and today <= d.expiry <= soon)})
    ev = doc_eval(store)
    return render(request, 'customer_portal/vendor/documents.html', {
        'page_title': 'Documents', 'profile': store, 'items': items, 'ev': ev,
        'min_date': (today + timedelta(days=1)).isoformat(),
    })


def vendor_document_file(request, pk):
    """Document dikhana: sirf store ka owner ya admin. Baqi ko 404 (andaza lagane se bachao)."""
    from ..security.permissions import has_matrix_perm
    doc = get_object_or_404(VendorDocument.objects.select_related('store'), pk=pk)
    u = request.user
    if not u.is_authenticated:
        raise Http404
    owner = getattr(u, 'vendor_profile', None)
    own = owner is not None and legal_profile(owner).pk == doc.store_id
    if not (u.is_superuser or own or has_matrix_perm(u, 'view_vendors')):
        raise Http404
    try:
        fh = doc.file.open('rb')
    except Exception:
        raise Http404
    resp = FileResponse(fh, content_type=mimetypes.guess_type(doc.file.name)[0] or 'application/octet-stream')
    resp['Content-Disposition'] = 'inline'
    resp['Cache-Control'] = 'private, no-store'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp
