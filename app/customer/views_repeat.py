"""Customer portal: repeat orders (daily / weekly). Reminder aata hai, ek tap par cart bhar jata hai."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..decorators import customer_login_required
from ..models import RepeatOrderPlan, SaleOrder
from . import repeat_plans
from .views_reorder import build_cart_from_order


def _customer(request):
    return request.user.customer_profile.customer if hasattr(request.user, 'customer_profile') else None


@customer_login_required
def repeat_plans_page(request):
    customer = _customer(request)
    if not customer:
        return redirect('shop_home')
    plans = list(RepeatOrderPlan.objects.filter(customer=customer).select_related('source_order'))
    for pl in plans:
        pl.schedule_text = repeat_plans.describe(pl)
    try:
        due_id = int(request.GET.get('due') or 0)
    except ValueError:
        due_id = 0
    return render(request, 'customer_portal/repeat_plans.html', {
        'plans': plans, 'due_id': due_id, 'weekdays': list(enumerate(repeat_plans.WEEKDAYS)),
    })


@customer_login_required
@require_POST
def repeat_plan_create(request, order_id):
    customer = _customer(request)
    if not customer:
        return redirect('shop_home')
    order = get_object_or_404(SaleOrder, pk=order_id, customer=customer)
    frequency = request.POST.get('frequency', 'daily')
    if frequency not in ('daily', 'weekly'):
        frequency = 'daily'
    try:
        weekday = min(max(int(request.POST.get('weekday', 0)), 0), 6)
        at = repeat_plans.parse_time(request.POST.get('time_of_day') or '08:00')
    except ValueError:
        messages.error(request, 'Please choose a valid time.')
        return redirect('order_detail_customer', order_id=order.id)
    if RepeatOrderPlan.objects.filter(customer=customer, is_active=True).count() >= repeat_plans.MAX_PLANS_PER_CUSTOMER:
        messages.error(request, f'You can have up to {repeat_plans.MAX_PLANS_PER_CUSTOMER} repeat orders. Delete one first.')
        return redirect('repeat_plans')
    items = list(order.items.select_related('product')[:5])
    names = [i.product.name for i in items[:2]]
    more = order.items.count() - len(names)
    store = ''
    try:
        from .store_orders import store_name
        store = store_name(order.vendor_id) if order.vendor_id else ''
    except Exception:
        pass
    plan = RepeatOrderPlan.objects.create(
        customer=customer, source_order=order, store_name=(store or '')[:150],
        summary=(', '.join(names) + (f' +{more}' if more > 0 else ''))[:250],
        frequency=frequency, weekday=weekday, time_of_day=at,
        next_run_at=repeat_plans.compute_next_run(frequency, weekday, at),
    )
    messages.success(request, f'Repeat order saved: {repeat_plans.describe(plan)}. We will remind you.')
    return redirect('repeat_plans')


def _own_plan(request, pk):
    return get_object_or_404(RepeatOrderPlan, pk=pk, customer=_customer(request))


@customer_login_required
@require_POST
def repeat_plan_toggle(request, pk):
    plan = _own_plan(request, pk)
    plan.is_active = not plan.is_active
    if plan.is_active:      # dobara chalu: agla waqt abhi se hisab karo
        plan.next_run_at = repeat_plans.compute_next_run(plan.frequency, plan.weekday, plan.time_of_day)
    plan.save(update_fields=['is_active', 'next_run_at'])
    return redirect('repeat_plans')


@customer_login_required
@require_POST
def repeat_plan_delete(request, pk):
    _own_plan(request, pk).delete()
    messages.success(request, 'Repeat order deleted.')
    return redirect('repeat_plans')


@customer_login_required
@require_POST
def repeat_plan_run(request, pk):
    """Ab hi cart mein daalo (reminder ya 'Order now' button)."""
    plan = _own_plan(request, pk)
    if not plan.source_order_id:
        messages.error(request, 'The original order is no longer available.')
        return redirect('repeat_plans')
    cart, skipped = build_cart_from_order(plan.source_order)
    if not cart:
        messages.error(request, 'None of the items in this order are available right now.')
        return redirect('repeat_plans')
    for k in ('buy_now_mode', 'buy_now_product_id'):
        request.session.pop(k, None)
    request.session['cart'] = cart
    request.session.modified = True
    if skipped:
        messages.warning(request, 'These items could not be added to the cart: ' + ', '.join(skipped))
    else:
        messages.success(request, 'Your repeat order is in the cart. Please review it and place the order.')
    return redirect('cart_view')
