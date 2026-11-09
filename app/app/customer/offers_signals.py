"""Order ki halat badalne par wallet ka kaam: delivered -> cashback, cancelled -> wallet wapas."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import SaleOrder
from . import offers

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SaleOrder, dispatch_uid='offers_wallet_on_order_status')
def wallet_on_order_status(sender, instance, **kwargs):
    try:
        offers.sync_status(instance)
    except Exception:        # wallet ki kisi galti se order kabhi na rukey
        logger.exception('Wallet signal error for order %s', getattr(instance, 'pk', None))
