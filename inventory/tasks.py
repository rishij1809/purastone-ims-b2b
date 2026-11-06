from celery import shared_task
import logging
from .integrations import ADAPTER_REGISTRY
from .models import Product, InventoryLedger, WholesaleOrder, Invoice
from .invoicing import generate_invoice_pdf
from django.utils import timezone
from django.db.models import Sum, Q

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5, default_retry_delay=2)
def sync_channel_inventory_task(self, sku: str, channel: str = None):
    """
    Asynchronously syncs stock quantities to external marketplaces,
    enforcing Redis-backed token bucket rate limits with Celery retries.
    """
    today = timezone.now().date()
    stock_stats = InventoryLedger.objects.filter(product_id=sku).aggregate(
        total=Sum('quantity'),
        expired=Sum('quantity', filter=Q(batch__expiry_date__lt=today)),
    )
    total_qty = stock_stats['total'] or 0
    expired_qty = stock_stats['expired'] or 0
    sellable_qty = max(0, total_qty - expired_qty)

    channels_to_sync = [channel] if channel and channel in ADAPTER_REGISTRY else list(ADAPTER_REGISTRY.keys())
    results = {}

    for ch in channels_to_sync:
        adapter = ADAPTER_REGISTRY[ch]
        try:
            res = adapter.sync_inventory(
                sku=sku,
                total_quantity=total_qty,
                sellable_quantity=sellable_qty,
                expired_quantity=expired_qty
            )
            results[ch] = res
        except RuntimeError as exc:
            logger.warning(f"Throttled on {ch} for SKU {sku}. Retrying task... Error: {exc}")
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    return results


@shared_task(bind=True, max_retries=3, default_retry_delay=2)
def generate_invoice_pdf_task(self, order_id: str):
    """
    Asynchronously generates a PDF invoice for a confirmed wholesale order
    and persists the URL to the Invoice model without blocking the main thread.
    """
    try:
        order = WholesaleOrder.objects.select_related('parent_wholesaler', 'child_wholesaler').get(id=order_id)
        pdf_url = generate_invoice_pdf(order)
        invoice, _ = Invoice.objects.update_or_create(
            order=order,
            defaults={'pdf_url': pdf_url}
        )
        logger.info(f"Successfully generated invoice PDF for wholesale order {order_id} at {pdf_url}")
        return {"order_id": order_id, "pdf_url": pdf_url}
    except Exception as exc:
        logger.error(f"Error generating invoice for order {order_id}: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
