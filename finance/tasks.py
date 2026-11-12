import logging
from celery import shared_task
from .materialized import ensure_and_refresh_materialized_views

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=2)
def refresh_financial_materialized_views_task(self):
    """Concurrently refreshes PostgreSQL Materialized Views and invalidates financial dashboard cache."""
    try:
        res = ensure_and_refresh_materialized_views()
        logger.info(f"Refreshed financial materialized views: {res}")
        return res
    except Exception as exc:
        logger.warning(f"Materialized view refresh failed: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task(bind=True, max_retries=3, default_retry_delay=2)
def sync_marketplace_settlement_task(self, channel: str, payload: dict):
    """
    Async Celery task processing marketplace order/settlement webhooks from:
    - SHOPIFY_D2C (Shopify GraphQL Admin + Razorpay/Stripe Payout)
    - AMAZON (Amazon SP-API Orders & Finances API)
    - FLIPKART (Flipkart Seller Settlement API)
    """
    from .services import OmnichannelIngestionService

    try:
        res = OmnichannelIngestionService.process_channel_payload(channel=channel, payload=payload)
        ensure_and_refresh_materialized_views()
        return res
    except Exception as exc:
        logger.error(f"Marketplace settlement sync error [{channel}]: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

