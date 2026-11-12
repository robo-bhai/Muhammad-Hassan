"""
Customer privacy: "Delete My Account" (Talabat jaisa).

Account delete karne par:
  * login band (user inactive, password unusable), naam/phone/email/address saaf
  * saved addresses, recently-viewed, profile photo hat jati hain
  * purane orders ke shipping/billing details saaf (amounts accounting ke liye rehte hain)
Delete NAHI hota jab tak: koi order chal raha ho, ya customer par bakaya raqam ho (Talabat bhi aise hi rokta hai).
"""
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, logout
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..decorators import customer_login_required
from ..models import CustomerOrder, SaleOrder

logger = logging.getLogger(__name__)

ACTIVE_SALE_STATUSES = ['pending', 'confirmed', 'processing', 'ready', 'partially_delivered']
ACTIVE_PORTAL_STATUSES = ['pending', 'confirmed', 'processing', 'packed', 'shipped', 'out_for_delivery']


def _blockers(customer):
    reasons = []
    if SaleOrder.objects.filter(customer=customer, status__in=ACTIVE_SALE_STATUSES).exists() or \
            CustomerOrder.objects.filter(customer=customer, status__in=ACTIVE_PORTAL_STATUSES).exists():
        reasons.append('You have an order in progress. Please wait until it is complete.')
    try:
        if customer.adjusted_outstanding_balance() > 0:
            reasons.append('You have an unpaid balance. Please settle it first.')
    except Exception:
        logger.exception('outstanding balance check failed')
    return reasons


@transaction.atomic
def _anonymize(request, profile, customer):
    user = profile.user

    # Customer record (accounting ke liye row rehti hai, personal data nahi)
    customer.name = 'Deleted Customer'
    for f in ('contact_number', 'email', 'address', 'ref_name_1', 'ref_contact_number_1',
              'ref_name_2', 'ref_contact_number_2'):
        setattr(customer, f, None)
    customer.save()

    # Portal orders: shipping / billing details saaf
    CustomerOrder.objects.filter(customer=customer).update(
        shipping_name='Deleted', shipping_phone='', shipping_address='', shipping_city='',
        shipping_state=None, shipping_postal_code=None, shipping_landmark=None,
        billing_name=None, billing_address=None)

    customer.addresses.all().delete()
    customer.recently_viewed.all().delete()

    if profile.profile_pic:
        try:
            profile.profile_pic.delete(save=False)
        except Exception:
            logger.exception('profile pic delete failed')
    profile.profile_pic = None
    profile.date_of_birth = None
    profile.gender = None
    profile.newsletter_subscribed = False
    profile.save()

    if user:
        user.is_active = False
        user.set_unusable_password()
        user.username = 'deleted_%s' % user.pk
        user.email = ''
        user.first_name = ''
        user.last_name = ''
        user.save()


@customer_login_required
@require_http_methods(['GET', 'POST'])
def delete_my_account(request):
    profile = getattr(request.user, 'customer_profile', None)
    if profile is None:
        return redirect('shop_home')
    customer = profile.customer
    blockers = _blockers(customer)

    if request.method == 'POST' and not blockers:
        if request.POST.get('confirm') != 'DELETE':
            messages.error(request, 'Type DELETE to confirm.')
        elif not authenticate(request, username=request.user.get_username(), password=request.POST.get('password', '')):
            messages.error(request, 'Incorrect password.')
        else:
            _anonymize(request, profile, customer)
            request.session.flush()
            logout(request)
            messages.success(request, 'Your account and personal data have been deleted.')
            return redirect('shop_home')

    return render(request, 'customer_portal/account/delete_account.html', {'blockers': blockers})
