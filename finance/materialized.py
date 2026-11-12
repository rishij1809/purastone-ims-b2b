from datetime import date
from django.core.cache import cache
from django.db import connection


MV_SQL_CREATE = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_channel_unit_economics AS
SELECT
    order_date,
    channel,
    COUNT(id) AS order_count,
    COALESCE(SUM(gross_sales_gmv), 0) AS gmv,
    COALESCE(SUM(gst_tax_amount), 0) AS gst_amount,
    COALESCE(SUM(discounts_and_rebates), 0) AS discounts,
    COALESCE(SUM(returns_and_rto_reversal), 0) AS rto_reversals,
    COALESCE(SUM(net_revenue), 0) AS net_revenue,
    COALESCE(SUM(batch_formulation_cogs), 0) AS batch_cogs,
    COALESCE(SUM(primary_packaging_cost), 0) AS packaging_cost,
    COALESCE(SUM(inward_freight_overhead), 0) AS inward_freight,
    COALESCE(SUM(cm1_amount), 0) AS cm1_amount,
    COALESCE(SUM(platform_commission_fees), 0) AS platform_fees,
    COALESCE(SUM(payment_gateway_fees), 0) AS gateway_fees,
    COALESCE(SUM(outbound_freight_cost), 0) AS outbound_freight,
    COALESCE(SUM(rto_reverse_freight_cost), 0) AS rto_freight,
    COALESCE(SUM(master_carton_and_pick_pack), 0) AS pick_pack_cost,
    COALESCE(SUM(transit_breakage_cost), 0) AS transit_breakage,
    COALESCE(SUM(cm2_amount), 0) AS cm2_amount
FROM fin_fact_order_unit_economics
GROUP BY order_date, channel;
"""

MV_SQL_UNIQUE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_channel_uniq
ON mv_daily_channel_unit_economics (order_date, channel);
"""


def bump_finance_cache() -> int:
    """Immediately bumps the finance cache namespace version."""
    cache_ver = int(cache.get("fin_cache_version", 1)) + 1
    cache.set("fin_cache_version", cache_ver, timeout=86400)
    return cache_ver


def ensure_and_refresh_materialized_views() -> dict:
    """
    On PostgreSQL: ensures mv_daily_channel_unit_economics exists and runs
    CONCURRENT refresh without blocking readers.
    On SQLite (local/serverless demo): bumps cache version key for sub-100ms cached queries.
    """
    new_ver = bump_finance_cache()

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(MV_SQL_CREATE)
            cursor.execute(MV_SQL_UNIQUE_IDX)
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_channel_unit_economics;")
        return {"backend": "postgresql", "materialized_view": "refreshed_concurrently", "cache_version": new_ver}

    return {"backend": connection.vendor, "cache_version": new_ver}


def query_mv_channel_totals(start_date: date, end_date: date) -> list | None:
    """Reads aggregated daily channel totals directly from the PostgreSQL Materialized View when available."""
    if connection.vendor != "postgresql":
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    channel,
                    SUM(order_count), SUM(gmv), SUM(gst_amount), SUM(discounts),
                    SUM(rto_reversals), SUM(net_revenue), SUM(batch_cogs),
                    SUM(packaging_cost), SUM(inward_freight), SUM(cm1_amount),
                    SUM(platform_fees), SUM(gateway_fees), SUM(outbound_freight),
                    SUM(rto_freight), SUM(pick_pack_cost), SUM(transit_breakage), SUM(cm2_amount)
                FROM mv_daily_channel_unit_economics
                WHERE order_date BETWEEN %s AND %s
                GROUP BY channel
                """,
                [start_date, end_date],
            )
            return cursor.fetchall()
    except Exception:
        return None


def make_finance_cache_key(prefix: str, *parts) -> str:
    ver = cache.get("fin_cache_version", 1)
    joined = ":".join(str(p) for p in parts)
    return f"fin:v{ver}:{prefix}:{joined}"
