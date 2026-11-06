import time
import logging
from django.conf import settings
import redis

logger = logging.getLogger(__name__)

class ChannelRateLimiter:
    """
    Token-bucket rate limiter backed by Redis with in-memory fallback.
    Ensures strict adherence to marketplace API rate limits.
    """
    _memory_buckets = {}
    _redis_client = None
    _redis_checked = False

    @classmethod
    def get_redis_client(cls):
        if cls._redis_checked:
            return cls._redis_client
        try:
            client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=0.2)
            client.ping()
            cls._redis_client = client
        except Exception:
            cls._redis_client = None
        finally:
            cls._redis_checked = True
        return cls._redis_client

    @classmethod
    def acquire(cls, channel: str, rate: float, burst: int = 1) -> bool:
        """
        Consumes 1 token for the specified channel.
        rate: tokens per second.
        burst: max bucket capacity.
        Returns True if permit granted immediately, False if throttled.
        """
        r = cls.get_redis_client()
        now = time.time()

        if r:
            key = f"ratelimit:{channel}"
            pipe = r.pipeline()
            pipe.hgetall(key)
            res = pipe.execute()[0]

            tokens = float(res.get(b'tokens', burst)) if res and b'tokens' in res else float(burst)
            last_updated = float(res.get(b'last_updated', now)) if res and b'last_updated' in res else now

            # Replenish
            elapsed = max(0.0, now - last_updated)
            tokens = min(burst, tokens + elapsed * rate)

            if tokens >= 1.0:
                tokens -= 1.0
                r.hmset(key, {'tokens': tokens, 'last_updated': now})
                r.expire(key, 60)
                return True
            return False
        else:
            # In-memory token bucket fallback
            bucket = cls._memory_buckets.get(channel, {'tokens': float(burst), 'last_updated': now})
            elapsed = max(0.0, now - bucket['last_updated'])
            bucket['tokens'] = min(float(burst), bucket['tokens'] + elapsed * rate)
            bucket['last_updated'] = now

            if bucket['tokens'] >= 1.0:
                bucket['tokens'] -= 1.0
                cls._memory_buckets[channel] = bucket
                return True
            cls._memory_buckets[channel] = bucket
            return False


class BaseMarketplaceAdapter:
    channel_name: str = ""
    rate_limit_per_sec: float = 2.0
    burst_limit: int = 5

    def sync_inventory(self, sku: str, total_quantity: int, sellable_quantity: int, expired_quantity: int) -> dict:
        allowed = ChannelRateLimiter.acquire(self.channel_name, self.rate_limit_per_sec, self.burst_limit)
        if not allowed:
            logger.warning(f"Rate limit exceeded for {self.channel_name}. Task should retry.")
            raise RuntimeError(f"{self.channel_name} rate limit reached. Throttling active.")

        logger.info(
            f"[{self.channel_name}] Synced SKU {sku}: Total={total_quantity}, "
            f"Sellable={sellable_quantity}, Expired={expired_quantity}"
        )
        return {
            "channel": self.channel_name,
            "sku": sku,
            "total_quantity": total_quantity,
            "sellable_quantity": sellable_quantity,
            "expired_quantity": expired_quantity,
            "status": "SUCCESS"
        }


class ShopifyAdapter(BaseMarketplaceAdapter):
    channel_name = "SHOPIFY"
    rate_limit_per_sec = 2.0
    burst_limit = 4


class AmazonSPAPIAdapter(BaseMarketplaceAdapter):
    channel_name = "AMAZON"
    rate_limit_per_sec = 2.0
    burst_limit = 5


class FlipkartAdapter(BaseMarketplaceAdapter):
    channel_name = "FLIPKART"
    rate_limit_per_sec = 5.0
    burst_limit = 10


ADAPTER_REGISTRY = {
    'SHOPIFY': ShopifyAdapter(),
    'AMAZON': AmazonSPAPIAdapter(),
    'FLIPKART': FlipkartAdapter(),
}
