from django.db.models.signals import post_save
from django.dispatch import receiver
from inventory.models import WholesaleOrder, Invoice
from .materialized import bump_finance_cache
from .models import (
    BatchExpiryWriteOff,
    FactOrderUnitEconomics,
    LorryReceipt,
    LossAndLeakageRecord,
    MarketingAndOpexEntry,
)
from .services import InternalErpHookService


@receiver(post_save, sender=WholesaleOrder)
def on_wholesale_order_saved(sender, instance: WholesaleOrder, **kwargs):
    if instance.status in ("CONFIRMED", "FULFILLED"):
        InternalErpHookService.sync_wholesale_order(instance)


@receiver(post_save, sender=Invoice)
def on_invoice_saved(sender, instance: Invoice, **kwargs):
    if instance.order and instance.order.status in ("CONFIRMED", "FULFILLED"):
        InternalErpHookService.sync_wholesale_order(instance.order)


@receiver(post_save, sender=LorryReceipt)
def on_lorry_receipt_saved(sender, instance: LorryReceipt, **kwargs):
    InternalErpHookService.sync_lorry_receipt(instance)


@receiver(post_save, sender=BatchExpiryWriteOff)
def on_batch_expiry_writeoff_saved(sender, instance: BatchExpiryWriteOff, **kwargs):
    InternalErpHookService.sync_batch_writeoff(instance)


@receiver(post_save, sender=FactOrderUnitEconomics)
@receiver(post_save, sender=LossAndLeakageRecord)
@receiver(post_save, sender=MarketingAndOpexEntry)
def on_finance_ledger_changed(sender, instance, **kwargs):
    bump_finance_cache()

