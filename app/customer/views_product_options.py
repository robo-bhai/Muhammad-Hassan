"""Vendor portal: product ke options (variants / add-ons) khud banana - Size, Extras waghera.

Ek hi page par sab kuch: group banao, option jodo, option "khatam" karo, hatao.
Sirf apne products par (product.vendor == vendor ka profile).
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import vendor_login_required
from ..models import Product, ProductOption, ProductOptionGroup

logger = logging.getLogger(__name__)

MAX_GROUPS = 10
MAX_SUBGROUPS = 20
MAX_OPTIONS = 30
MAX_PRICE = Decimal('99999.99')


def _price(value):
    """'150' -> Decimal; khali = 0. Galat ya manfi raqam par None."""
    value = (value or '').strip()
    if not value:
        return Decimal('0.00')
    try:
        d = Decimal(value).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None
    if d < 0 or d > MAX_PRICE:
        return None
    return d


@vendor_login_required
def vendor_product_options(request, pk):
    profile = request.user.vendor_profile
    product = get_object_or_404(Product, pk=pk, vendor=profile.vendor)

    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action', '')
        try:
            _handle(request, product, action)
        except Exception:
            logger.exception('Product options error')
            messages.error(request, '❌ Something went wrong. Please try again')
        return redirect('vendor_product_options', pk=product.pk)

    groups = product.option_groups.filter(parent_option__isnull=True).prefetch_related(
        'options', 'options__child_groups', 'options__child_groups__options')
    return render(request, 'customer_portal/vendor/product_options.html', {
        'product': product,
        'groups': groups,
        'max_groups': MAX_GROUPS,
        'max_options': MAX_OPTIONS,
    })


def _handle(request, product, action):
    post = request.POST

    if action == 'add_group':
        name = (post.get('name') or '').strip()[:60]
        if not name:
            messages.error(request, '❌ Enter a group name (e.g. Size)')
            return
        # Sub-choice: group sirf tab dikhega jab parent option chuna ho (sirf ek level, top-level group ke option par)
        parent = None
        if post.get('parent_option_id'):
            parent = get_object_or_404(ProductOption, pk=post.get('parent_option_id'),
                                       group__product=product, group__parent_option__isnull=True)
            if product.option_groups.filter(parent_option__isnull=False).count() >= MAX_SUBGROUPS:
                messages.error(request, f'❌ A product can have at most {MAX_SUBGROUPS} sub-choice groups')
                return
        elif product.option_groups.filter(parent_option__isnull=True).count() >= MAX_GROUPS:
            messages.error(request, f'❌ A product can have at most {MAX_GROUPS} groups')
            return
        kind = post.get('kind') if post.get('kind') in ('single', 'multiple') else 'single'
        try:
            max_select = max(0, min(int(post.get('max_select') or 0), 50))
        except ValueError:
            max_select = 0
        ProductOptionGroup.objects.create(
            product=product, name=name, kind=kind,
            is_required=bool(post.get('is_required')),
            max_select=max_select if kind == 'multiple' else 0,
            sort_order=product.option_groups.filter(parent_option=parent).count(),
            parent_option=parent,
        )
        messages.success(request, f'✅ Group "{name}" created. Now add options to it.')
        return

    # baqi sab actions kisi group/option par hain, jo isi product ka hona chahiye
    if action in ('delete_group', 'add_option'):
        group = get_object_or_404(ProductOptionGroup, pk=post.get('group_id'), product=product)
        if action == 'delete_group':
            group.delete()
            messages.success(request, '✅ Group removed.')
            return
        name = (post.get('name') or '').strip()[:60]
        price = _price(post.get('extra_price'))
        if not name:
            messages.error(request, '❌ Enter an option name')
        elif price is None:
            messages.error(request, '❌ Extra price is not valid (0 to 99999.99)')
        elif group.options.count() >= MAX_OPTIONS:
            messages.error(request, f'❌ A group can have at most {MAX_OPTIONS} options')
        else:
            ProductOption.objects.create(group=group, name=name, extra_price=price,
                                         sort_order=group.options.count())
            messages.success(request, f'✅ "{name}" added.')
        return

    if action in ('delete_option', 'toggle_option'):
        option = get_object_or_404(ProductOption, pk=post.get('option_id'), group__product=product)
        if action == 'delete_option':
            option.delete()
            messages.success(request, '✅ Option removed.')
        else:
            option.is_available = not option.is_available
            option.save(update_fields=['is_available'])
            messages.success(request, '✅ ' + (f'"{option.name}" dobara available.' if option.is_available
                                              else f'"{option.name}" khatam mark ho gaya.'))
        return
