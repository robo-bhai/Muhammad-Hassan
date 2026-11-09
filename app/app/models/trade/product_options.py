"""Models: trade/product_options - product variants aur add-ons (size, flavour, extra cheese...).

ProductOptionGroup: ek product ka sawal, jaise "Size chunein" ya "Extras".
    kind='single'   -> sirf ek option chun sakte hain (radio: Small / Medium / Large)
    kind='multiple' -> kai options (checkbox: Extra cheese, Raita, Cold drink)
ProductOption: group ka ek jawab, uski extra price ke sath (0 = muft).

Price ka qaida: product ki asal price + chune hue options ki extra_price = item ki price.
"""
from decimal import Decimal

from django.db import models

from ..inventory.catalog import Product


class ProductOptionGroup(models.Model):
    KIND_CHOICES = [
        ('single', 'Ek chunein (jaise Size)'),
        ('multiple', 'Kai chunein (jaise Extras)'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='option_groups')
    name = models.CharField(max_length=60, help_text="Jaise: Size, Flavour, Extras")
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default='single')
    is_required = models.BooleanField(
        default=False, help_text="ON = customer ko chunna lazmi hai (jaise Size)")
    max_select = models.PositiveSmallIntegerField(
        default=0, help_text="'Kai chunein' mein ziyada se ziyada kitne (0 = koi hadd nahi)")
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Chhota number pehle nazar aata hai")
    is_active = models.BooleanField(default=True)
    # Sub-choices: group sirf tab dikhta hai jab ye option chuna ho (jaise "Combo" chunne par "Drink" group)
    parent_option = models.ForeignKey(
        'ProductOption', null=True, blank=True, on_delete=models.CASCADE, related_name='child_groups',
        help_text="Khali = hamesha dikhao. Option chunein to ye group sirf tab dikhega jab wo option chuna ho")

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Product Option Group'
        verbose_name_plural = 'Product Option Groups'

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class ProductOption(models.Model):
    group = models.ForeignKey(ProductOptionGroup, on_delete=models.CASCADE, related_name='options')
    name = models.CharField(max_length=60, help_text="Jaise: Large, Extra cheese")
    extra_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Product ki price mein itni raqam jur jayegi (0 = muft)")
    is_available = models.BooleanField(
        default=True, help_text="OFF = abhi khatam, customer ko nazar aayega par chun nahi sakega")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Product Option'
        verbose_name_plural = 'Product Options'

    def __str__(self):
        extra = f" (+{self.extra_price})" if self.extra_price else ""
        return f"{self.name}{extra}"


def ordered_groups(product):
    """Product page ke liye groups: har sub-choice group apne parent group ke bilkul neeche."""
    groups = list(product.option_groups.filter(is_active=True).prefetch_related('options'))
    by_parent = {}
    for g in groups:
        by_parent.setdefault(g.parent_option_id, []).append(g)

    out, seen = [], set()

    def walk(group_list):
        for g in group_list:
            if g.id in seen:
                continue
            seen.add(g.id)
            out.append(g)
            for opt in g.options.all():
                walk(by_parent.get(opt.id, []))

    walk(by_parent.get(None, []))
    # bachay hue (parent hat gaya ya nonactive group ke neeche) bhi aakhir mein: lekin ye dikhte nahi
    return out


def resolve_selection(product, selected_ids):
    """Customer ke chune hue option ids ko jaanch kar (options, extra_total, error) lauta deta hai.

    - Sirf is product ke active groups ke options maane jate hain (dusre product ki id chalegi nahi)
    - Lazmi group ka jawab na ho, 'single' mein ek se ziyada hon, ya max_select paar ho to error
    - Khatam (is_available=False) option chun'ne par error
    - Sub-choice group (parent_option wala) sirf tab active hai jab uska parent option chuna ho:
      active nahi to us ke options chunna galat hai, aur lazmi hone ka qaida bhi laagu nahi hota
    Price server par nikalti hai, customer ki bheji hui price par kabhi bharosa nahi.
    """
    try:
        ids = {int(i) for i in (selected_ids or [])}
    except (TypeError, ValueError):
        return [], Decimal('0.00'), 'Options sahi nahi hain'

    groups = list(product.option_groups.filter(is_active=True).prefetch_related('options'))
    valid = {o.id: o for g in groups for o in g.options.all()}
    if ids - set(valid):
        return [], Decimal('0.00'), 'Koi option is product ka nahi hai'

    chosen, total = [], Decimal('0.00')
    for g in groups:
        picked = [valid[i] for i in sorted(ids) if valid[i].group_id == g.id]
        active = g.parent_option_id is None or g.parent_option_id in ids
        if not active:
            if picked:
                return [], Decimal('0.00'), f'"{g.name}" sirf tab chun sakte hain jab pehla option chuna ho'
            continue
        if g.is_required and not picked:
            return [], Decimal('0.00'), f'"{g.name}" chunna lazmi hai'
        if g.kind == 'single' and len(picked) > 1:
            return [], Decimal('0.00'), f'"{g.name}" mein sirf ek option chun sakte hain'
        if g.kind == 'multiple' and g.max_select and len(picked) > g.max_select:
            return [], Decimal('0.00'), f'"{g.name}" mein ziyada se ziyada {g.max_select} chun sakte hain'
        for o in picked:
            if not o.is_available:
                return [], Decimal('0.00'), f'"{o.name}" abhi available nahi'
            chosen.append(o)
            total += o.extra_price
    return chosen, total, None
