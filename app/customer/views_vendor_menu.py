"""Vendor portal: store ka menu tarteeb dena - sections ka order aur Popular items.

Sections = product categories. Vendor up/down se tarteeb tay karta hai; jis category ki row na ho
wo aakhir mein naam ki tarteeb se aati hai. Popular = vendor ke chune hue items store page ke
sab se upar "Popular" section mein dikhte hain.
"""
import logging

from django.contrib import messages
from .vendor_access import get_vendor_profile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import vendor_login_required
from ..models import Product, StoreMenuSection

logger = logging.getLogger(__name__)

MAX_POPULAR = 8


def vendor_categories(profile):
    """Is vendor ki (live ya pending) products ki categories, vendor ke tay kiye order mein."""
    cats = {}
    for p in Product.objects.filter(vendor=profile.vendor, category__isnull=False).select_related('category'):
        cats[p.category_id] = p.category
    order = dict(StoreMenuSection.objects.filter(store=profile).values_list('category_id', 'sort_order'))
    big = 10 ** 6
    return sorted(cats.values(), key=lambda c: (order.get(c.id, big), c.name.lower()))


@vendor_login_required
def vendor_menu(request):
    profile = get_vendor_profile(request.user)
    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')

    if request.method == 'POST':
        try:
            _handle(request, profile)
        except Exception:
            logger.exception('Vendor menu error')
            messages.error(request, '❌ Something went wrong. Please try again')
        return redirect('vendor_menu')

    cats = vendor_categories(profile)
    products = list(Product.objects.filter(vendor=profile.vendor).select_related('category').order_by('name'))
    return render(request, 'customer_portal/vendor/menu.html', {
        'profile': profile,
        'categories': cats,
        'products': products,
        'popular_count': sum(1 for p in products if p.is_popular),
        'max_popular': MAX_POPULAR,
    })


def _handle(request, profile):
    post = request.POST
    action = post.get('action', '')

    if action in ('up', 'down'):
        cats = vendor_categories(profile)
        ids = [c.id for c in cats]
        try:
            cid = int(post.get('category_id'))
        except (TypeError, ValueError):
            return
        if cid not in ids:
            return
        i = ids.index(cid)
        j = i - 1 if action == 'up' else i + 1
        if j < 0 or j >= len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        # poori tarteeb 0,1,2.. dobara likh dein (taake purani adhoori rows se gadbad na ho)
        with transaction.atomic():
            for n, c_id in enumerate(ids):
                StoreMenuSection.objects.update_or_create(
                    store=profile, category_id=c_id, defaults={'sort_order': n})
        return

    if action == 'toggle_popular':
        product = get_object_or_404(Product, pk=post.get('product_id'), vendor=profile.vendor)
        if not product.is_popular:
            if Product.objects.filter(vendor=profile.vendor, is_popular=True).count() >= MAX_POPULAR:
                messages.error(request, f'❌ You can keep at most {MAX_POPULAR} popular items')
                return
        product.is_popular = not product.is_popular
        product.save(update_fields=['is_popular'])
        messages.success(request, f'⭐ "{product.name}" ' + ('Added to Popular.' if product.is_popular else 'Popular se hata diya.'))
