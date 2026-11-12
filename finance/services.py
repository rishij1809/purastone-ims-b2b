import csv
import io
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone

from inventory.models import (
    Product, Batch, InventoryLedger, TransactionLog, WholesaleOrder, WholesalerParent
)
from .materialized import (
    ensure_and_refresh_materialized_views,
    make_finance_cache_key,
    query_mv_channel_totals,
)
from .models import (
    ZERO,
    _q2,
    ApprovalStatus,
    BatchExpiryWriteOff,
    CM3_MARKETING_BUCKETS,
    ChannelSkuMapping,
    ExpenseBucket,
    FactOrderUnitEconomics,
    FinancialAuditLog,
    FinancialTreasuryConfig,
    LorryReceipt,
    LossAndLeakageRecord,
    LossCategory,
    ManualRevenueEntry,
    MarketingAndOpexEntry,
    OrderBatchAllocation,
    ReconciliationStatus,
    SalesChannel,
)
from django.core.cache import cache


def resolve_date_range(preset: str = "MTD", start_str: str = None, end_str: str = None):
    """Resolves preset ('TODAY','7D','MTD','QTD','YTD','CUSTOM') into current and prior periods."""
    today = timezone.now().date()
    p = (preset or "MTD").upper()

    if p == "TODAY":
        start, end = today, today
    elif p == "7D":
        start, end = today - timedelta(days=6), today
    elif p == "MTD":
        start, end = today.replace(day=1), today
    elif p == "QTD":
        q_month = ((today.month - 1) // 3) * 3 + 1
        start, end = today.replace(month=q_month, day=1), today
    elif p == "YTD":
        # Indian FY starts April 1; calendar fallback also common — support FY starting Apr 1
        fy_year = today.year if today.month >= 4 else today.year - 1
        start, end = date(fy_year, 4, 1), today
    elif p == "ALL":
        start, end = today - timedelta(days=365), today
    elif p == "CUSTOM" and start_str and end_str:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
    else:
        start, end = today.replace(day=1), today

    if end < start:
        start, end = end, start

    span_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span_days - 1)
    return start, end, prev_start, prev_end


class InternalErpHookService:
    """
    Synchronizes internal B2B Wholesaler ERP orders, Invoices, TMS LorryReceipts,
    POD breakages, and FEFO batch expiry write-offs into Module 9 sub-ledgers.
    """

    @classmethod
    @transaction.atomic
    def sync_wholesale_order(cls, order: WholesaleOrder) -> FactOrderUnitEconomics | None:
        if order.status not in ("CONFIRMED", "FULFILLED"):
            return None

        order_date = order.updated_at.date() if order.updated_at else timezone.now().date()
        ref = order.po_number or f"B2B-{str(order.id)[:8].upper()}"

        items = list(order.items.select_related("product").all())
        total_units = sum(i.quantity for i in items) or 1
        primary_sku = items[0].product if items else None

        # Rule-based provisional Tier 3 & Tier 4 overheads
        est_packaging = _q2(Decimal(total_units) * Decimal("15.00"))
        est_inward_freight = _q2(Decimal(total_units) * Decimal("6.00"))
        est_pick_pack = _q2(Decimal(total_units) * Decimal("12.00"))
        est_b2b_freight = _q2(max(Decimal("450.00"), Decimal(total_units) * Decimal("18.00")))

        existing = FactOrderUnitEconomics.objects.filter(
            channel=SalesChannel.B2B_WHOLESALE, wholesale_order=order
        ).first()

        # Preserve verified LR values if already linked & reconciled
        reconcile_status = existing.reconciliation_status if existing else ReconciliationStatus.PROVISIONAL
        outbound_freight = existing.outbound_freight_cost if (existing and existing.lorry_receipt) else est_b2b_freight
        pick_pack = existing.master_carton_and_pick_pack if (existing and existing.lorry_receipt) else est_pick_pack
        breakage = existing.transit_breakage_cost if existing else ZERO

        defaults = {
            "order_date": order_date,
            "external_order_ref": ref,
            "reconciliation_status": reconcile_status,
            "b2b_retailer": order.parent_wholesaler,
            "b2b_branch": order.child_wholesaler,
            "primary_sku": primary_sku,
            "gross_sales_gmv": _q2(order.subtotal + order.total_gst),
            "gst_tax_amount": _q2(order.total_gst),
            "discounts_and_rebates": _q2(order.discount_amount),
            "returns_and_rto_reversal": existing.returns_and_rto_reversal if existing else ZERO,
            "batch_formulation_cogs": _q2(order.total_cogs),
            "primary_packaging_cost": est_packaging,
            "inward_freight_overhead": est_inward_freight,
            "outbound_freight_cost": outbound_freight,
            "master_carton_and_pick_pack": pick_pack,
            "transit_breakage_cost": breakage,
            "payment_due_date": existing.payment_due_date if existing else (order_date + timedelta(days=30)),
            "amount_collected": existing.amount_collected if existing else ZERO,
        }

        econ, _ = FactOrderUnitEconomics.objects.update_or_create(
            wholesale_order=order,
            defaults={"channel": SalesChannel.B2B_WHOLESALE, **defaults},
        )

        # Populate SKU & FEFO Batch Allocations
        if not econ.batch_allocations.exists():
            cls._create_b2b_batch_allocations(econ, order, items, est_packaging + est_inward_freight, outbound_freight + pick_pack)

        transaction.on_commit(lambda: ensure_and_refresh_materialized_views())
        return econ

    @staticmethod
    def _create_b2b_batch_allocations(econ, order, items, total_pkg_inward: Decimal, total_fulfill: Decimal):
        total_units = sum(i.quantity for i in items) or 1
        order_discount_ratio = (
            order.final_value / order.subtotal if order.subtotal > ZERO else Decimal("1.00")
        )
        for item in items:
            # Find recent FEFO WHOLESALE outtake logs for this product to attribute exact batches
            logs = list(
                TransactionLog.objects.filter(
                    product=item.product,
                    source="WHOLESALE",
                    transaction_type="OUTTAKE",
                    timestamp__gte=order.created_at - timedelta(minutes=5),
                )
                .select_related("batch")
                .order_by("-timestamp")
            )
            remaining = item.quantity
            allocated_batches = []
            for lg in logs:
                if remaining <= 0:
                    break
                qty_here = min(abs(lg.quantity_change), remaining)
                if qty_here > 0:
                    allocated_batches.append((lg.batch, qty_here))
                    remaining -= qty_here

            if remaining > 0:
                fallback_batch = Batch.objects.filter(product=item.product).order_by("expiry_date").first()
                allocated_batches.append((fallback_batch, remaining))

            unit_net_rev = _q2(item.locked_b2b_price * order_discount_ratio)
            for batch_obj, qty_here in allocated_batches:
                share = Decimal(qty_here) / Decimal(total_units)
                OrderBatchAllocation.objects.create(
                    order_econ=econ,
                    product=item.product,
                    batch=batch_obj,
                    units_dispatched=qty_here,
                    unit_batch_cost=item.locked_base_cost,
                    line_net_revenue=_q2(unit_net_rev * Decimal(qty_here)),
                    line_packaging_and_inward=_q2(total_pkg_inward * share),
                    line_fulfillment_cost=_q2(total_fulfill * share),
                )

    @classmethod
    @transaction.atomic
    def sync_lorry_receipt(cls, lr: LorryReceipt) -> None:
        if not lr.wholesale_order:
            return
        econ = FactOrderUnitEconomics.objects.filter(wholesale_order=lr.wholesale_order).first()
        if not econ:
            econ = cls.sync_wholesale_order(lr.wholesale_order)
        if not econ:
            return

        econ.lorry_receipt = lr
        econ.outbound_freight_cost = _q2(lr.freight_amount) if lr.freight_mode == "PAID_PREPAID" else ZERO
        econ.master_carton_and_pick_pack = _q2(lr.ancillary_packaging_cost)
        econ.transit_breakage_cost = _q2(lr.pod_damage_cost)

        if lr.pod_status in ("CLEAN", "DAMAGED") and lr.pod_verified_at:
            econ.reconciliation_status = ReconciliationStatus.RECONCILED
            econ.settled_at = lr.pod_verified_at
            econ.settlement_utr = lr.lr_number
            econ.actual_settled_payout = econ.expected_payout_amount

        econ.save()

        # Auto-log POD damage to LossAndLeakageRecord
        if lr.pod_damage_cost > ZERO:
            batch_obj = None
            first_alloc = econ.batch_allocations.select_related("batch").first()
            if first_alloc:
                batch_obj = first_alloc.batch
            LossAndLeakageRecord.objects.update_or_create(
                linked_order_econ=econ,
                category=LossCategory.TRANSIT_LR_BREAKAGE,
                is_manual_entry=False,
                defaults={
                    "incurred_date": (lr.pod_verified_at.date() if lr.pod_verified_at else timezone.now().date()),
                    "channel": SalesChannel.B2B_WHOLESALE,
                    "affected_batch": batch_obj,
                    "units_lost": lr.pod_damage_units,
                    "total_loss_amount": _q2(lr.pod_damage_cost),
                    "reason_notes": lr.pod_notes or f"POD Transit Damage on LR {lr.lr_number} ({lr.transporter_name})",
                    "approval_status": ApprovalStatus.APPROVED,
                },
            )

        transaction.on_commit(lambda: ensure_and_refresh_materialized_views())

    @classmethod
    @transaction.atomic
    def sync_batch_writeoff(cls, writeoff: BatchExpiryWriteOff) -> LossAndLeakageRecord:
        record, _ = LossAndLeakageRecord.objects.update_or_create(
            affected_batch=writeoff.batch,
            incurred_date=writeoff.writeoff_date,
            category=LossCategory.FEFO_BATCH_EXPIRY,
            is_manual_entry=False,
            defaults={
                "channel": SalesChannel.B2B_WHOLESALE,
                "units_lost": writeoff.units_written_off,
                "total_loss_amount": writeoff.total_writeoff_value,
                "reason_notes": writeoff.notes or f"FEFO Batch Expiry Write-Off ({writeoff.batch.batch_id})",
                "approval_status": ApprovalStatus.APPROVED,
                "created_by": writeoff.created_by,
                "approved_by": writeoff.created_by,
            },
        )
        transaction.on_commit(lambda: ensure_and_refresh_materialized_views())
        return record


class OmnichannelIngestionService:
    """
    Handles Shopify GraphQL + Razorpay/Stripe, Amazon SP-API, and Flipkart Seller
    Settlement order creation (PROVISIONAL) and payout reconciliation (RECONCILED/DISPUTED).
    """

    DEFAULT_CHANNEL_RULES = {
        SalesChannel.SHOPIFY_D2C: {"comm_pct": Decimal("0.00"), "pg_pct": Decimal("2.15"), "ship": Decimal("75.00")},
        SalesChannel.AMAZON: {"comm_pct": Decimal("18.00"), "pg_pct": Decimal("0.00"), "ship": Decimal("92.00")},
        SalesChannel.FLIPKART: {"comm_pct": Decimal("16.50"), "pg_pct": Decimal("0.00"), "ship": Decimal("88.00")},
    }

    @classmethod
    @transaction.atomic
    def ingest_provisional_order(
        cls,
        channel: str,
        external_order_ref: str,
        order_date: date,
        items: list,
        gross_sales_gmv: Decimal,
        gst_tax_amount: Decimal,
        discounts_and_rebates: Decimal = ZERO,
        outbound_freight_override: Decimal = None,
        deduct_stock: bool = False,
        user=None,
    ) -> FactOrderUnitEconomics:
        """
        Creates/updates a PROVISIONAL FactOrderUnitEconomics row using ChannelSkuMapping
        and multi-batch FEFO formulation costs.
        """
        from inventory.services import InventoryEngine

        rules = cls.DEFAULT_CHANNEL_RULES.get(channel, {"comm_pct": ZERO, "pg_pct": ZERO, "ship": ZERO})
        gross = _q2(Decimal(gross_sales_gmv))
        gst = _q2(Decimal(gst_tax_amount))
        discounts = _q2(Decimal(discounts_and_rebates))
        net_rev = _q2(gross - gst - discounts)

        total_batch_cogs = ZERO
        total_pkg = ZERO
        total_inward = ZERO
        total_comm = ZERO
        total_units = 0
        alloc_specs = []

        for item in items:
            qty = int(item.get("quantity", 1))
            total_units += qty
            ext_id = item.get("external_product_id")
            sku_code = item.get("sku")

            mapping = None
            if ext_id:
                mapping = ChannelSkuMapping.objects.select_related("internal_sku").filter(
                    channel=channel, external_product_id=ext_id, is_active=True
                ).first()
            if not mapping and sku_code:
                mapping = ChannelSkuMapping.objects.select_related("internal_sku").filter(
                    channel=channel, external_sku_code=sku_code, is_active=True
                ).first()

            product = mapping.internal_sku if mapping else Product.objects.get(sku=sku_code)
            pkg_per_unit = mapping.default_packaging_cost_per_unit if mapping else Decimal("18.00")
            inward_per_unit = mapping.default_inward_freight_per_unit if mapping else Decimal("8.00")
            comm_pct = (
                mapping.default_platform_commission_pct
                if (mapping and mapping.default_platform_commission_pct > ZERO)
                else rules["comm_pct"]
            )

            line_gross = _q2(Decimal(str(item.get("line_gross", gross / max(1, len(items))))))
            total_comm += _q2(line_gross * (comm_pct / Decimal("100.00")))
            total_pkg += _q2(pkg_per_unit * Decimal(qty))
            total_inward += _q2(inward_per_unit * Decimal(qty))

            # Explicit multi-batch cost splits if supplied or FEFO outtake
            if item.get("batch_splits"):
                for sp in item["batch_splits"]:
                    b_qty = int(sp["quantity"])
                    b_cost = _q2(Decimal(str(sp.get("unit_cost", product.base_cost))))
                    b_obj = Batch.objects.filter(batch_id=sp["batch_id"]).first()
                    total_batch_cogs += _q2(Decimal(b_qty) * b_cost)
                    alloc_specs.append((product, b_obj, b_qty, b_cost))
            elif deduct_stock:
                src = "AMAZON" if channel == SalesChannel.AMAZON else ("FLIPKART" if channel == SalesChannel.FLIPKART else "SHOPIFY")
                out = InventoryEngine.outtake(sku=product.sku, quantity=qty, source=src, user=user)
                for pick in out["pick_directions"]:
                    p_qty = int(pick["quantity_picked"])
                    b_obj = Batch.objects.filter(batch_id=pick["batch_id"]).first()
                    b_cost = product.base_cost
                    total_batch_cogs += _q2(Decimal(p_qty) * b_cost)
                    alloc_specs.append((product, b_obj, p_qty, b_cost))
            else:
                b_obj = Batch.objects.filter(product=product, expiry_date__gte=order_date).order_by("expiry_date").first()
                b_cost = _q2(Decimal(str(item.get("unit_cost", product.base_cost))))
                total_batch_cogs += _q2(Decimal(qty) * b_cost)
                alloc_specs.append((product, b_obj, qty, b_cost))

        est_pg_fee = _q2((gross - discounts) * (rules["pg_pct"] / Decimal("100.00")))
        est_ship = _q2(outbound_freight_override) if outbound_freight_override is not None else rules["ship"]
        est_pick_pack = _q2(Decimal(max(1, total_units)) * Decimal("14.00"))
        primary_sku = alloc_specs[0][0] if alloc_specs else None

        econ, _ = FactOrderUnitEconomics.objects.update_or_create(
            channel=channel,
            external_order_ref=external_order_ref,
            defaults={
                "order_date": order_date,
                "reconciliation_status": ReconciliationStatus.PROVISIONAL,
                "primary_sku": primary_sku,
                "gross_sales_gmv": gross,
                "gst_tax_amount": gst,
                "discounts_and_rebates": discounts,
                "returns_and_rto_reversal": ZERO,
                "batch_formulation_cogs": _q2(total_batch_cogs),
                "primary_packaging_cost": _q2(total_pkg),
                "inward_freight_overhead": _q2(total_inward),
                "platform_commission_fees": _q2(total_comm),
                "payment_gateway_fees": est_pg_fee,
                "outbound_freight_cost": est_ship,
                "rto_reverse_freight_cost": ZERO,
                "master_carton_and_pick_pack": est_pick_pack,
                "transit_breakage_cost": ZERO,
            },
        )

        econ.batch_allocations.all().delete()
        unit_denom = Decimal(max(1, total_units))
        for prod, b_obj, qty_here, u_cost in alloc_specs:
            share = Decimal(qty_here) / unit_denom
            OrderBatchAllocation.objects.create(
                order_econ=econ,
                product=prod,
                batch=b_obj,
                units_dispatched=qty_here,
                unit_batch_cost=u_cost,
                line_net_revenue=_q2(net_rev * share),
                line_packaging_and_inward=_q2((total_pkg + total_inward) * share),
                line_fulfillment_cost=_q2(econ.total_direct_fulfillment_cost * share),
            )

        transaction.on_commit(lambda: ensure_and_refresh_materialized_views())
        return econ

    @classmethod
    @transaction.atomic
    def reconcile_settlement(
        cls,
        channel: str,
        external_order_ref: str,
        actual_settled_payout: Decimal,
        settlement_utr: str,
        platform_commission_fees: Decimal = None,
        payment_gateway_fees: Decimal = None,
        outbound_freight_cost: Decimal = None,
        rto_reverse_freight_cost: Decimal = None,
        returns_and_rto_reversal: Decimal = None,
        is_rto: bool = False,
        rto_inventory_returned: bool = True,
        extra_sla_penalty: Decimal = ZERO,
        fee_tolerance: Decimal = Decimal("5.00"),
        actor=None,
    ) -> FactOrderUnitEconomics:
        """
        Atomically transitions a PROVISIONAL order to RECONCILED (or DISPUTED on overcharge / missing RTO).
        """
        econ = FactOrderUnitEconomics.objects.select_for_update().get(
            channel=channel, external_order_ref=external_order_ref
        )
        provisional_expected_payout = econ.expected_payout_amount

        if platform_commission_fees is not None:
            econ.platform_commission_fees = _q2(Decimal(platform_commission_fees))
        if payment_gateway_fees is not None:
            econ.payment_gateway_fees = _q2(Decimal(payment_gateway_fees))
        if outbound_freight_cost is not None:
            econ.outbound_freight_cost = _q2(Decimal(outbound_freight_cost))
        if rto_reverse_freight_cost is not None:
            econ.rto_reverse_freight_cost = _q2(Decimal(rto_reverse_freight_cost))
        if returns_and_rto_reversal is not None:
            econ.returns_and_rto_reversal = _q2(Decimal(returns_and_rto_reversal))

        econ.is_rto = is_rto
        econ.rto_inventory_returned = rto_inventory_returned
        econ.actual_settled_payout = _q2(Decimal(actual_settled_payout))
        econ.settlement_utr = settlement_utr
        econ.settled_at = timezone.now()
        econ.amount_collected = econ.actual_settled_payout

        # Compute waterfall & expected payout with verified fees
        econ.recalculate_waterfall()
        payout_diff = _q2(econ.expected_payout_amount - econ.actual_settled_payout)
        provisional_fee_variance = _q2(provisional_expected_payout - econ.actual_settled_payout)

        dispute_reasons = []
        if abs(payout_diff) > fee_tolerance:
            dispute_reasons.append(f"Settlement Payout Mismatch (₹{payout_diff})")
        if is_rto and not rto_inventory_returned:
            dispute_reasons.append("Unreturned RTO Inventory")
        if Decimal(extra_sla_penalty) > ZERO:
            dispute_reasons.append(f"SLA Penalty Charged (₹{extra_sla_penalty})")

        if dispute_reasons:
            econ.reconciliation_status = ReconciliationStatus.DISPUTED
            econ.discrepancy_reason = " | ".join(dispute_reasons)
        else:
            econ.reconciliation_status = ReconciliationStatus.RECONCILED
            econ.discrepancy_reason = (
                f"Reconciled (Provisional vs Actual Variance ₹{provisional_fee_variance})"
                if provisional_fee_variance != ZERO
                else ""
            )

        econ.save()

        # Sync updated Net Rev / Fulfillment to Batch Allocations
        allocs = list(econ.batch_allocations.all())
        total_u = sum(a.units_dispatched for a in allocs) or 1
        for a in allocs:
            share = Decimal(a.units_dispatched) / Decimal(total_u)
            a.line_net_revenue = _q2(econ.net_revenue * share)
            a.line_fulfillment_cost = _q2(econ.total_direct_fulfillment_cost * share)
            a.save()

        # Log unreturned RTO inventory loss or SLA penalty
        if is_rto and not rto_inventory_returned and econ.batch_formulation_cogs > ZERO:
            first_alloc = allocs[0] if allocs else None
            LossAndLeakageRecord.objects.update_or_create(
                linked_order_econ=econ,
                category=LossCategory.UNRETURNED_RTO_LOSS,
                is_manual_entry=False,
                defaults={
                    "incurred_date": timezone.now().date(),
                    "channel": channel,
                    "affected_batch": first_alloc.batch if first_alloc else None,
                    "units_lost": sum(a.units_dispatched for a in allocs),
                    "total_loss_amount": econ.batch_formulation_cogs,
                    "reason_notes": f"Unreturned RTO inventory for {external_order_ref} (UTR {settlement_utr})",
                    "approval_status": ApprovalStatus.APPROVED,
                },
            )
        if Decimal(extra_sla_penalty) > ZERO:
            LossAndLeakageRecord.objects.create(
                incurred_date=timezone.now().date(),
                category=LossCategory.MARKETPLACE_SLA_PENALTY,
                channel=channel,
                linked_order_econ=econ,
                total_loss_amount=_q2(Decimal(extra_sla_penalty)),
                is_manual_entry=False,
                reason_notes=f"Marketplace SLA / Chargeback on {external_order_ref}",
                approval_status=ApprovalStatus.APPROVED,
            )

        FinancialAuditLog.record(
            actor=actor,
            action="DISPUTE" if dispute_reasons else "RECONCILE",
            entity_type="FactOrderUnitEconomics",
            entity_id=str(econ.id),
            snapshot={
                "channel": channel,
                "external_order_ref": external_order_ref,
                "status": econ.reconciliation_status,
                "actual_settled_payout": str(econ.actual_settled_payout),
                "discrepancy_amount": str(econ.discrepancy_amount),
                "cm2_amount": str(econ.cm2_amount),
            },
            notes=econ.discrepancy_reason or f"Settled via UTR {settlement_utr}",
        )
        transaction.on_commit(lambda: ensure_and_refresh_materialized_views())
        return econ

    @classmethod
    def process_channel_payload(cls, channel: str, payload: dict, actor=None) -> dict:
        """Unified adapter handling order creation & settlement events across Shopify, Amazon, Flipkart."""
        event_type = payload.get("event_type", "ORDER_AND_SETTLEMENT").upper()
        ref = payload["external_order_ref"]
        order_date = date.fromisoformat(payload.get("order_date", timezone.now().date().isoformat()))

        if event_type in ("ORDER_CREATED", "ORDER_AND_SETTLEMENT"):
            econ = cls.ingest_provisional_order(
                channel=channel,
                external_order_ref=ref,
                order_date=order_date,
                items=payload.get("items", []),
                gross_sales_gmv=Decimal(str(payload.get("gross_sales_gmv", "0.00"))),
                gst_tax_amount=Decimal(str(payload.get("gst_tax_amount", "0.00"))),
                discounts_and_rebates=Decimal(str(payload.get("discounts_and_rebates", "0.00"))),
                outbound_freight_override=(
                    Decimal(str(payload["estimated_shipping"]))
                    if payload.get("estimated_shipping") is not None
                    else None
                ),
                deduct_stock=bool(payload.get("deduct_stock", False)),
                user=actor,
            )
        if event_type in ("SETTLEMENT_VERIFIED", "ORDER_AND_SETTLEMENT") and payload.get("settlement"):
            s = payload["settlement"]
            econ = cls.reconcile_settlement(
                channel=channel,
                external_order_ref=ref,
                actual_settled_payout=Decimal(str(s["actual_settled_payout"])),
                settlement_utr=s["settlement_utr"],
                platform_commission_fees=(
                    Decimal(str(s["platform_commission_fees"])) if s.get("platform_commission_fees") is not None else None
                ),
                payment_gateway_fees=(
                    Decimal(str(s["payment_gateway_fees"])) if s.get("payment_gateway_fees") is not None else None
                ),
                outbound_freight_cost=(
                    Decimal(str(s["outbound_freight_cost"])) if s.get("outbound_freight_cost") is not None else None
                ),
                rto_reverse_freight_cost=(
                    Decimal(str(s["rto_reverse_freight_cost"])) if s.get("rto_reverse_freight_cost") is not None else None
                ),
                returns_and_rto_reversal=(
                    Decimal(str(s["returns_and_rto_reversal"])) if s.get("returns_and_rto_reversal") is not None else None
                ),
                is_rto=bool(s.get("is_rto", False)),
                rto_inventory_returned=bool(s.get("rto_inventory_returned", True)),
                extra_sla_penalty=Decimal(str(s.get("extra_sla_penalty", "0.00"))),
                actor=actor,
            )

        return {
            "status": "OK",
            "channel": channel,
            "external_order_ref": ref,
            "reconciliation_status": econ.reconciliation_status,
            "net_revenue": str(econ.net_revenue),
            "cm1_amount": str(econ.cm1_amount),
            "cm2_amount": str(econ.cm2_amount),
        }


class WaterfallAnalyticsService:
    """
    Aggregates the 6-Tier Financial Waterfall (GMV -> Net Rev -> CM1 -> CM2 -> CM3 -> EBITDA -> Net Profit),
    prorates multi-day OPEX & Ad Spend, and powers all 6 Financial Command Center views.
    """

    @staticmethod
    def _prorate_expenses(start_date: date, end_date: date) -> dict:
        """
        Prorates APPROVED MarketingAndOpexEntry records overlapping [start_date, end_date]
        proportionally by overlapping days, and segments into CM3 marketing vs Fixed OPEX.
        """
        entries = MarketingAndOpexEntry.objects.filter(
            approval_status=ApprovalStatus.APPROVED,
            period_start_date__lte=end_date,
            period_end_date__gte=start_date,
        )

        cm3_total = ZERO
        cm3_by_channel = {ch: ZERO for ch, _ in SalesChannel.choices}
        cm3_shared = ZERO
        cm3_buckets = {}

        opex_total = ZERO
        opex_buckets = {}

        for e in entries:
            total_entry_days = max(1, (e.period_end_date - e.period_start_date).days + 1)
            overlap_start = max(start_date, e.period_start_date)
            overlap_end = min(end_date, e.period_end_date)
            overlap_days = max(0, (overlap_end - overlap_start).days + 1)
            prorated_amt = _q2(
                Decimal(e.amount_exclusive_gst) * (Decimal(overlap_days) / Decimal(total_entry_days))
            )

            if e.is_cm3_marketing_cost:
                cm3_total += prorated_amt
                cm3_buckets[e.bucket] = _q2(cm3_buckets.get(e.bucket, ZERO) + prorated_amt)
                if e.target_channel:
                    cm3_by_channel[e.target_channel] = _q2(
                        cm3_by_channel.get(e.target_channel, ZERO) + prorated_amt
                    )
                else:
                    cm3_shared += prorated_amt
            else:
                opex_total += prorated_amt
                opex_buckets[e.bucket] = _q2(opex_buckets.get(e.bucket, ZERO) + prorated_amt)

        return {
            "cm3_marketing_total": _q2(cm3_total),
            "cm3_by_channel": cm3_by_channel,
            "cm3_shared": _q2(cm3_shared),
            "cm3_buckets": cm3_buckets,
            "fixed_opex_total": _q2(opex_total),
            "opex_buckets": opex_buckets,
        }

    @classmethod
    def _compute_period_waterfall(cls, start_date: date, end_date: date) -> dict:
        orders = FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date))
        agg = orders.aggregate(
            order_count=Count("id"),
            gmv=Sum("gross_sales_gmv"),
            gst=Sum("gst_tax_amount"),
            discounts=Sum("discounts_and_rebates"),
            rto_reversals=Sum("returns_and_rto_reversal"),
            net_revenue=Sum("net_revenue"),
            batch_cogs=Sum("batch_formulation_cogs"),
            packaging=Sum("primary_packaging_cost"),
            inward_freight=Sum("inward_freight_overhead"),
            total_direct_cogs=Sum("total_direct_cogs"),
            cm1=Sum("cm1_amount"),
            platform_fees=Sum("platform_commission_fees"),
            gateway_fees=Sum("payment_gateway_fees"),
            outbound_freight=Sum("outbound_freight_cost"),
            rto_freight=Sum("rto_reverse_freight_cost"),
            pick_pack=Sum("master_carton_and_pick_pack"),
            breakage=Sum("transit_breakage_cost"),
            total_fulfillment=Sum("total_direct_fulfillment_cost"),
            cm2=Sum("cm2_amount"),
            collected=Sum("amount_collected"),
        )

        gmv = _q2(agg["gmv"])
        gst = _q2(agg["gst"])
        discounts = _q2(agg["discounts"])
        rto_reversals = _q2(agg["rto_reversals"])
        net_revenue = _q2(agg["net_revenue"])

        batch_cogs = _q2(agg["batch_cogs"])
        packaging = _q2(agg["packaging"])
        inward_freight = _q2(agg["inward_freight"])
        total_direct_cogs = _q2(agg["total_direct_cogs"])
        cm1 = _q2(agg["cm1"])

        platform_fees = _q2(agg["platform_fees"])
        gateway_fees = _q2(agg["gateway_fees"])
        outbound_freight = _q2(agg["outbound_freight"])
        rto_freight = _q2(agg["rto_freight"])
        pick_pack = _q2(agg["pick_pack"])
        breakage = _q2(agg["breakage"])
        total_fulfillment = _q2(agg["total_fulfillment"])
        cm2 = _q2(agg["cm2"])

        expenses = cls._prorate_expenses(start_date, end_date)
        losses_qs = LossAndLeakageRecord.objects.filter(
            incurred_date__range=(start_date, end_date),
            approval_status=ApprovalStatus.APPROVED,
        )
        tester_promo_loss = _q2(
            losses_qs.filter(category=LossCategory.TESTER_PROMO_BURN).aggregate(s=Sum("total_loss_amount"))["s"]
        )
        # Non-order losses exclude TESTER_PROMO_BURN (in CM3) and linked TRANSIT_LR_BREAKAGE (already in CM2)
        non_order_losses = _q2(
            losses_qs.exclude(category=LossCategory.TESTER_PROMO_BURN)
            .exclude(category=LossCategory.TRANSIT_LR_BREAKAGE, linked_order_econ__isnull=False)
            .aggregate(s=Sum("total_loss_amount"))["s"]
        )
        total_all_losses = _q2(losses_qs.aggregate(s=Sum("total_loss_amount"))["s"])

        cm3_deductions = _q2(expenses["cm3_marketing_total"] + tester_promo_loss)
        cm3 = _q2(cm2 - cm3_deductions)

        fixed_opex = expenses["fixed_opex_total"]
        ebitda = _q2(cm3 - fixed_opex - non_order_losses)

        treasury, _ = FinancialTreasuryConfig.objects.get_or_create(pk=1)
        span_days = max(1, (end_date - start_date).days + 1)
        prorated_interest = _q2(treasury.monthly_interest_expense * (Decimal(span_days) / Decimal("30.00")))
        pre_tax = ebitda - prorated_interest
        tax_expense = _q2(pre_tax * (treasury.effective_tax_rate_pct / Decimal("100.00"))) if pre_tax > ZERO else ZERO
        interest_and_taxes = _q2(prorated_interest + tax_expense)
        net_profit = _q2(ebitda - interest_and_taxes)

        def pct(num):
            return _q2((num / net_revenue) * Decimal("100.00")) if net_revenue > ZERO else ZERO

        collected_cash = _q2(agg["collected"])
        net_cash_flow = _q2(collected_cash - total_fulfillment - expenses["cm3_marketing_total"] - fixed_opex - prorated_interest - tax_expense)

        return {
            "order_count": agg["order_count"] or 0,
            "gmv": gmv,
            "gst": gst,
            "discounts": discounts,
            "rto_reversals": rto_reversals,
            "net_revenue": net_revenue,
            "batch_cogs": batch_cogs,
            "packaging": packaging,
            "inward_freight": inward_freight,
            "total_direct_cogs": total_direct_cogs,
            "cm1": cm1,
            "cm1_pct": pct(cm1),
            "platform_fees": platform_fees,
            "gateway_fees": gateway_fees,
            "outbound_freight": outbound_freight,
            "rto_freight": rto_freight,
            "pick_pack": pick_pack,
            "breakage": breakage,
            "total_fulfillment": total_fulfillment,
            "cm2": cm2,
            "cm2_pct": pct(cm2),
            "marketing_ad_spend": expenses["cm3_marketing_total"],
            "tester_promo_loss": tester_promo_loss,
            "cm3_deductions": cm3_deductions,
            "cm3": cm3,
            "cm3_pct": pct(cm3),
            "fixed_opex": fixed_opex,
            "non_order_losses": non_order_losses,
            "total_all_losses": total_all_losses,
            "ebitda": ebitda,
            "ebitda_pct": pct(ebitda),
            "interest_and_taxes": interest_and_taxes,
            "net_profit": net_profit,
            "net_profit_pct": pct(net_profit),
            "net_cash_flow": net_cash_flow,
            "expenses_meta": expenses,
        }

    @classmethod
    def get_command_center_summary(cls, start_date: date, end_date: date, prev_start: date = None, prev_end: date = None) -> dict:
        cache_key = make_finance_cache_key("cmd", start_date, end_date)
        cached = cache.get(cache_key)
        if cached:
            return cached

        if prev_start is None or prev_end is None:
            span = (end_date - start_date).days + 1
            prev_end = start_date - timedelta(days=1)
            prev_start = prev_end - timedelta(days=span - 1)

        cur = cls._compute_period_waterfall(start_date, end_date)
        prev = cls._compute_period_waterfall(prev_start, prev_end)

        def delta_pct(c_val, p_val):
            if p_val == ZERO:
                return 100.0 if c_val > ZERO else 0.0
            return float(_q2(((c_val - p_val) / abs(p_val)) * Decimal("100.00")))

        # Omnichannel Matrix (uses Materialized View on PG when present, ORM fallback on SQLite)
        mv_rows = query_mv_channel_totals(start_date, end_date)
        channel_stats = {}
        if mv_rows is not None:
            for row in mv_rows:
                ch = row[0]
                channel_stats[ch] = {
                    "orders": int(row[1]),
                    "gmv": _q2(row[2]),
                    "net_revenue": _q2(row[6]),
                    "cogs": _q2(Decimal(row[7]) + Decimal(row[8]) + Decimal(row[9])),
                    "cm1": _q2(row[10]),
                    "fulfillment": _q2(Decimal(row[11]) + Decimal(row[12]) + Decimal(row[13]) + Decimal(row[14]) + Decimal(row[15]) + Decimal(row[16])),
                    "cm2": _q2(row[17]),
                }
        else:
            rows = (
                FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date))
                .values("channel")
                .annotate(
                    orders=Count("id"),
                    gmv=Sum("gross_sales_gmv"),
                    net_revenue=Sum("net_revenue"),
                    cogs=Sum("total_direct_cogs"),
                    cm1=Sum("cm1_amount"),
                    fulfillment=Sum("total_direct_fulfillment_cost"),
                    cm2=Sum("cm2_amount"),
                )
            )
            for r in rows:
                channel_stats[r["channel"]] = {
                    "orders": r["orders"],
                    "gmv": _q2(r["gmv"]),
                    "net_revenue": _q2(r["net_revenue"]),
                    "cogs": _q2(r["cogs"]),
                    "cm1": _q2(r["cm1"]),
                    "fulfillment": _q2(r["fulfillment"]),
                    "cm2": _q2(r["cm2"]),
                }

        exp_meta = cur["expenses_meta"]
        total_net_rev = cur["net_revenue"]
        ch_matrix = []
        for ch_code, ch_label in SalesChannel.choices:
            st = channel_stats.get(
                ch_code,
                {"orders": 0, "gmv": ZERO, "net_revenue": ZERO, "cogs": ZERO, "cm1": ZERO, "fulfillment": ZERO, "cm2": ZERO},
            )
            rev_share = (st["net_revenue"] / total_net_rev) if total_net_rev > ZERO else Decimal("0.20")
            ch_mkt = _q2(exp_meta["cm3_by_channel"].get(ch_code, ZERO) + (exp_meta["cm3_shared"] * rev_share))
            ch_cm3 = _q2(st["cm2"] - ch_mkt)
            ch_cm1_pct = float(_q2((st["cm1"] / st["net_revenue"]) * Decimal("100.00"))) if st["net_revenue"] > ZERO else 0.0
            ch_cm2_pct = float(_q2((st["cm2"] / st["net_revenue"]) * Decimal("100.00"))) if st["net_revenue"] > ZERO else 0.0
            ch_cm3_pct = float(_q2((ch_cm3 / st["net_revenue"]) * Decimal("100.00"))) if st["net_revenue"] > ZERO else 0.0

            ch_matrix.append({
                "channel": ch_code,
                "label": ch_label,
                "orders": st["orders"],
                "gmv": f"{st['gmv']:.2f}",
                "net_revenue": f"{st['net_revenue']:.2f}",
                "cm1": f"{st['cm1']:.2f}",
                "cm1_pct": ch_cm1_pct,
                "cm2": f"{st['cm2']:.2f}",
                "cm2_pct": ch_cm2_pct,
                "marketing_allocated": f"{ch_mkt:.2f}",
                "cm3": f"{ch_cm3:.2f}",
                "cm3_pct": ch_cm3_pct,
            })

        # Real-Time Founder Anomaly Ticker
        anomalies = cls._build_anomaly_ticker(start_date, end_date)

        # Waterfall Bridge steps
        waterfall_bridge = [
            {"step": "Gross Sales (GMV)", "amount": float(cur["gmv"]), "type": "positive"},
            {"step": "GST & Indirect Taxes", "amount": float(-cur["gst"]), "type": "deduction"},
            {"step": "Discounts & Rebates", "amount": float(-cur["discounts"]), "type": "deduction"},
            {"step": "Returns & RTO Reversals", "amount": float(-cur["rto_reversals"]), "type": "deduction"},
            {"step": "Net Revenue", "amount": float(cur["net_revenue"]), "type": "subtotal"},
            {"step": "Direct Batch COGS + Pkg + Inward", "amount": float(-cur["total_direct_cogs"]), "type": "deduction"},
            {"step": "CM1 (Product Margin)", "amount": float(cur["cm1"]), "type": "subtotal"},
            {"step": "Platform, PG, Freight, Breakage", "amount": float(-cur["total_fulfillment"]), "type": "deduction"},
            {"step": "CM2 (Operational Margin)", "amount": float(cur["cm2"]), "type": "subtotal"},
            {"step": "Performance Ads, Comm & Testers", "amount": float(-cur["cm3_deductions"]), "type": "deduction"},
            {"step": "CM3 (Post-Marketing)", "amount": float(cur["cm3"]), "type": "subtotal"},
            {"step": "Fixed OPEX & Non-Order Losses", "amount": float(-(cur["fixed_opex"] + cur["non_order_losses"])), "type": "deduction"},
            {"step": "EBITDA", "amount": float(cur["ebitda"]), "type": "subtotal"},
            {"step": "Interest & Taxes", "amount": float(-cur["interest_and_taxes"]), "type": "deduction"},
            {"step": "Net Profit (PAT)", "amount": float(cur["net_profit"]), "type": "final"},
        ]

        result = {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "kpis": {
                "order_count": cur["order_count"],
                "gmv": f"{cur['gmv']:.2f}",
                "net_revenue": f"{cur['net_revenue']:.2f}",
                "cm1": f"{cur['cm1']:.2f}",
                "cm1_pct": float(cur["cm1_pct"]),
                "cm2": f"{cur['cm2']:.2f}",
                "cm2_pct": float(cur["cm2_pct"]),
                "cm3": f"{cur['cm3']:.2f}",
                "cm3_pct": float(cur["cm3_pct"]),
                "ebitda": f"{cur['ebitda']:.2f}",
                "ebitda_pct": float(cur["ebitda_pct"]),
                "net_profit": f"{cur['net_profit']:.2f}",
                "net_profit_pct": float(cur["net_profit_pct"]),
                "total_losses": f"{cur['total_all_losses']:.2f}",
                "net_cash_flow": f"{cur['net_cash_flow']:.2f}",
            },
            "deltas": {
                "gmv_pct": delta_pct(cur["gmv"], prev["gmv"]),
                "net_revenue_pct": delta_pct(cur["net_revenue"], prev["net_revenue"]),
                "cm1_pct": delta_pct(cur["cm1"], prev["cm1"]),
                "cm2_pct": delta_pct(cur["cm2"], prev["cm2"]),
                "cm3_pct": delta_pct(cur["cm3"], prev["cm3"]),
                "net_profit_pct": delta_pct(cur["net_profit"], prev["net_profit"]),
            },
            "waterfall_bridge": waterfall_bridge,
            "waterfall_detail": {k: f"{v:.2f}" if isinstance(v, Decimal) else v for k, v in cur.items() if k != "expenses_meta"},
            "omnichannel_matrix": ch_matrix,
            "anomalies": anomalies,
        }
        cache.set(cache_key, result, timeout=60)
        return result

    @staticmethod
    def _build_anomaly_ticker(start_date: date, end_date: date) -> list:
        today = timezone.now().date()
        anomalies = []

        # 1. Negative CM2 orders
        neg_orders = FactOrderUnitEconomics.objects.filter(
            order_date__range=(start_date, end_date), cm2_amount__lt=ZERO
        ).select_related("primary_sku")[:5]
        for o in neg_orders:
            sku_label = o.primary_sku.sku if o.primary_sku else o.external_order_ref
            anomalies.append({
                "severity": "CRITICAL",
                "type": "NEGATIVE_CM2",
                "message": f"Negative CM2 Alert: {o.channel} order {o.external_order_ref} ({sku_label}) bled ₹{abs(o.cm2_amount):.2f}",
            })

        # 2. High RTO spikes (> 15%)
        ch_rto = (
            FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date))
            .values("channel")
            .annotate(total=Count("id"), rtos=Count("id", filter=Q(is_rto=True)))
        )
        for c in ch_rto:
            if c["total"] > 0:
                rate = (c["rtos"] / c["total"]) * 100.0
                if rate >= 15.0:
                    anomalies.append({
                        "severity": "WARNING",
                        "type": "HIGH_RTO_SPIKE",
                        "message": f"High RTO Spike on {c['channel']}: {rate:.1f}% ({c['rtos']}/{c['total']} orders returned)",
                    })

        # 3. Near-expiry batch value at risk (next 45 days)
        near_cutoff = today + timedelta(days=45)
        near_batches = (
            InventoryLedger.objects.filter(
                quantity__gt=0, batch__expiry_date__gte=today, batch__expiry_date__lte=near_cutoff
            )
            .select_related("product", "batch")
        )
        risk_val = ZERO
        risk_units = 0
        for led in near_batches:
            risk_units += led.quantity
            risk_val += Decimal(led.quantity) * led.product.base_cost
        if risk_units > 0:
            anomalies.append({
                "severity": "WARNING",
                "type": "EXPIRY_RISK",
                "message": f"Near-Expiry Batch Value at Risk (<45d): {risk_units} units worth ₹{risk_val:.2f} COGS",
            })

        # 4. Overdue B2B Retailer Receivables
        overdue = FactOrderUnitEconomics.objects.filter(
            channel=SalesChannel.B2B_WHOLESALE,
            payment_due_date__lt=today,
        ).select_related("b2b_retailer")
        overdue_amt = ZERO
        overdue_cnt = 0
        for b2b in overdue:
            bal = b2b.expected_payout_amount - b2b.amount_collected
            if bal > ZERO:
                overdue_amt += bal
                overdue_cnt += 1
        if overdue_cnt > 0:
            anomalies.append({
                "severity": "CRITICAL",
                "type": "OVERDUE_AR",
                "message": f"Overdue B2B Receivables: {overdue_cnt} invoices totaling ₹{overdue_amt:.2f} past 30-day terms",
            })

        # 5. Disputed marketplace settlements
        disputed_cnt = FactOrderUnitEconomics.objects.filter(
            reconciliation_status=ReconciliationStatus.DISPUTED
        ).count()
        if disputed_cnt > 0:
            anomalies.append({
                "severity": "WARNING",
                "type": "DISPUTED_SETTLEMENT",
                "message": f"{disputed_cnt} marketplace settlement(s) flagged DISPUTED (fee overcharge / missing RTO)",
            })

        return anomalies

    @classmethod
    def get_unit_economics_explorer(cls, start_date: date, end_date: date) -> dict:
        allocs = (
            OrderBatchAllocation.objects.filter(order_econ__order_date__range=(start_date, end_date))
            .select_related("product", "batch", "order_econ")
        )

        sku_map = {}
        batch_rows = []
        for a in allocs:
            s_key = a.product.sku
            if s_key not in sku_map:
                sku_map[s_key] = {
                    "sku": s_key,
                    "product_name": a.product.name,
                    "base_cost_catalog": float(a.product.base_cost),
                    "units": 0,
                    "net_revenue": ZERO,
                    "batch_cogs": ZERO,
                    "pkg_inward": ZERO,
                    "fulfillment": ZERO,
                    "cm1": ZERO,
                    "cm2": ZERO,
                }
            m = sku_map[s_key]
            m["units"] += a.units_dispatched
            m["net_revenue"] += a.line_net_revenue
            m["batch_cogs"] += a.total_batch_cogs
            m["pkg_inward"] += a.line_packaging_and_inward
            m["fulfillment"] += a.line_fulfillment_cost
            m["cm1"] += a.line_cm1
            m["cm2"] += a.line_cm2

            if a.batch:
                variance = _q2(a.unit_batch_cost - a.product.base_cost)
                batch_rows.append({
                    "batch_id": a.batch.batch_id,
                    "sku": s_key,
                    "channel": a.order_econ.channel,
                    "order_ref": a.order_econ.external_order_ref,
                    "units": a.units_dispatched,
                    "catalog_unit_cost": f"{a.product.base_cost:.2f}",
                    "actual_batch_unit_cost": f"{a.unit_batch_cost:.2f}",
                    "cost_variance_per_unit": f"{variance:.2f}",
                    "line_net_revenue": f"{a.line_net_revenue:.2f}",
                    "line_cm1": f"{a.line_cm1:.2f}",
                    "line_cm2": f"{a.line_cm2:.2f}",
                })

        sku_rankings = []
        for s in sku_map.values():
            rev = s["net_revenue"]
            cm1_pct = float(_q2((s["cm1"] / rev) * Decimal("100.00"))) if rev > ZERO else 0.0
            cm2_pct = float(_q2((s["cm2"] / rev) * Decimal("100.00"))) if rev > ZERO else 0.0
            if s["cm2"] < ZERO or cm2_pct < 5.0:
                tier = "MARGIN_BLEEDER"
            elif cm2_pct >= 25.0 and s["cm2"] > ZERO:
                tier = "HERO_SKU"
            else:
                tier = "STEADY"

            sku_rankings.append({
                "sku": s["sku"],
                "product_name": s["product_name"],
                "units_sold": s["units"],
                "net_revenue": float(_q2(rev)),
                "batch_cogs": float(_q2(s["batch_cogs"])),
                "cm1": float(_q2(s["cm1"])),
                "cm1_pct": cm1_pct,
                "cm2": float(_q2(s["cm2"])),
                "cm2_pct": cm2_pct,
                "classification": tier,
            })

        sku_rankings.sort(key=lambda x: x["cm2"], reverse=True)
        return {"sku_rankings": sku_rankings, "batch_variance": batch_rows[:100]}

    @classmethod
    def get_settlement_reconciler(cls, start_date: date, end_date: date, channel: str = None, status_filter: str = None) -> dict:
        qs = FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date)).order_by("-order_date", "-updated_at")
        if channel and channel != "ALL":
            qs = qs.filter(channel=channel)
        if status_filter and status_filter != "ALL":
            qs = qs.filter(reconciliation_status=status_filter)

        summary_agg = FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date)).aggregate(
            provisional_count=Count("id", filter=Q(reconciliation_status=ReconciliationStatus.PROVISIONAL)),
            reconciled_count=Count("id", filter=Q(reconciliation_status=ReconciliationStatus.RECONCILED)),
            disputed_count=Count("id", filter=Q(reconciliation_status=ReconciliationStatus.DISPUTED)),
            provisional_hold_amount=Sum("expected_payout_amount", filter=Q(reconciliation_status=ReconciliationStatus.PROVISIONAL)),
            total_discrepancy=Sum("discrepancy_amount", filter=Q(reconciliation_status=ReconciliationStatus.DISPUTED)),
        )

        rows = []
        for o in qs[:200]:
            rows.append({
                "id": str(o.id),
                "order_date": o.order_date.isoformat(),
                "channel": o.channel,
                "external_order_ref": o.external_order_ref,
                "reconciliation_status": o.reconciliation_status,
                "gmv": f"{o.gross_sales_gmv:.2f}",
                "net_revenue": f"{o.net_revenue:.2f}",
                "platform_fees": f"{o.platform_commission_fees:.2f}",
                "gateway_fees": f"{o.payment_gateway_fees:.2f}",
                "freight_and_rto": f"{(o.outbound_freight_cost + o.rto_reverse_freight_cost):.2f}",
                "expected_payout": f"{o.expected_payout_amount:.2f}",
                "actual_payout": f"{o.actual_settled_payout:.2f}",
                "discrepancy": f"{o.discrepancy_amount:.2f}",
                "discrepancy_reason": o.discrepancy_reason,
                "is_rto": o.is_rto,
                "rto_inventory_returned": o.rto_inventory_returned,
                "settlement_utr": o.settlement_utr,
                "cm2_amount": f"{o.cm2_amount:.2f}",
            })

        return {
            "summary": {
                "provisional_count": summary_agg["provisional_count"] or 0,
                "reconciled_count": summary_agg["reconciled_count"] or 0,
                "disputed_count": summary_agg["disputed_count"] or 0,
                "provisional_hold_amount": f"{_q2(summary_agg['provisional_hold_amount']):.2f}",
                "total_discrepancy": f"{_q2(summary_agg['total_discrepancy']):.2f}",
            },
            "orders": rows,
        }

    @classmethod
    def get_losses_intelligence(cls, start_date: date, end_date: date) -> dict:
        qs = LossAndLeakageRecord.objects.filter(
            incurred_date__range=(start_date, end_date),
            approval_status=ApprovalStatus.APPROVED,
        ).select_related("affected_batch", "affected_batch__product")

        by_cat = {}
        for cat_code, cat_label in LossCategory.choices:
            by_cat[cat_code] = {"category": cat_code, "label": cat_label, "amount": ZERO, "units": 0, "count": 0}

        for r in qs:
            c = by_cat[r.category]
            c["amount"] += r.total_loss_amount
            c["units"] += r.units_lost
            c["count"] += 1

        # 4 Executive Pillars
        pillars = {
            "fefo_expiry_and_qc": _q2(
                by_cat[LossCategory.FEFO_BATCH_EXPIRY]["amount"] + by_cat[LossCategory.QC_LAB_REJECTION]["amount"]
            ),
            "transit_and_rto_breakage": _q2(
                by_cat[LossCategory.TRANSIT_LR_BREAKAGE]["amount"] + by_cat[LossCategory.UNRETURNED_RTO_LOSS]["amount"]
            ),
            "promo_tester_burn": _q2(by_cat[LossCategory.TESTER_PROMO_BURN]["amount"]),
            "bad_debt_sla_and_manual": _q2(
                by_cat[LossCategory.BAD_DEBT_WRITEOFF]["amount"]
                + by_cat[LossCategory.MARKETPLACE_SLA_PENALTY]["amount"]
                + by_cat[LossCategory.MANUAL_WAREHOUSE_LOSS]["amount"]
            ),
        }

        records = [
            {
                "id": str(r.id),
                "incurred_date": r.incurred_date.isoformat(),
                "category": r.category,
                "category_label": r.get_category_display(),
                "channel": r.channel,
                "batch_id": r.affected_batch.batch_id if r.affected_batch else None,
                "units_lost": r.units_lost,
                "total_loss_amount": f"{r.total_loss_amount:.2f}",
                "is_manual_entry": r.is_manual_entry,
                "reason_notes": r.reason_notes,
            }
            for r in qs.order_by("-incurred_date", "-created_at")[:100]
        ]

        return {
            "pillars": {k: f"{v:.2f}" for k, v in pillars.items()},
            "total_losses": f"{sum(pillars.values()):.2f}",
            "by_category": [
                {**v, "amount": f"{_q2(v['amount']):.2f}"} for v in by_cat.values()
            ],
            "records": records,
        }

    @classmethod
    def get_working_capital_and_runway(cls, start_date: date, end_date: date) -> dict:
        today = timezone.now().date()
        treasury, _ = FinancialTreasuryConfig.objects.get_or_create(pk=1)
        waterfall = cls._compute_period_waterfall(start_date, end_date)

        # 1. B2B AR Aging (0-30, 31-60, 61-90, 90+ days past invoice / due date)
        aging = {"0_30": ZERO, "31_60": ZERO, "61_90": ZERO, "90_plus": ZERO}
        b2b_receivables = []
        b2b_orders = FactOrderUnitEconomics.objects.filter(
            channel=SalesChannel.B2B_WHOLESALE
        ).select_related("b2b_retailer")

        total_ar = ZERO
        for o in b2b_orders:
            outstanding = _q2(o.expected_payout_amount - o.amount_collected)
            if outstanding > ZERO:
                total_ar += outstanding
                age_days = max(0, (today - o.order_date).days)
                if age_days <= 30:
                    aging["0_30"] += outstanding
                elif age_days <= 60:
                    aging["31_60"] += outstanding
                elif age_days <= 90:
                    aging["61_90"] += outstanding
                else:
                    aging["90_plus"] += outstanding

                b2b_receivables.append({
                    "order_ref": o.external_order_ref,
                    "retailer": o.b2b_retailer.name if o.b2b_retailer else "B2B Account",
                    "order_date": o.order_date.isoformat(),
                    "due_date": o.payment_due_date.isoformat() if o.payment_due_date else None,
                    "age_days": age_days,
                    "outstanding": f"{outstanding:.2f}",
                })

        # Marketplace pending payouts
        marketplace_receivable = _q2(
            FactOrderUnitEconomics.objects.filter(
                channel__in=[SalesChannel.AMAZON, SalesChannel.FLIPKART, SalesChannel.SHOPIFY_D2C],
                reconciliation_status=ReconciliationStatus.PROVISIONAL,
            ).aggregate(s=Sum("expected_payout_amount"))["s"]
        )

        # 2. Transporter & Vendor AP Payables
        lr_payables = _q2(
            LorryReceipt.objects.filter(transporter_payable_status="PENDING").aggregate(
                s=Sum("freight_amount")
            )["s"]
        )
        opex_payables = _q2(
            MarketingAndOpexEntry.objects.filter(
                approval_status=ApprovalStatus.APPROVED, is_paid=False
            ).aggregate(s=Sum("amount_exclusive_gst"))["s"]
        )
        total_ap = _q2(lr_payables + opex_payables)

        # 3. Capital Locked in Unexpired & Expired Inventory Batches
        inv_capital = ZERO
        sellable_inv_capital = ZERO
        for led in InventoryLedger.objects.filter(quantity__gt=0).select_related("product", "batch"):
            val = _q2(Decimal(led.quantity) * led.product.base_cost)
            inv_capital += val
            if led.batch.expiry_date >= today:
                sellable_inv_capital += val

        # 4. Monthly Burn & Runway Calculator
        span_days = max(1, (end_date - start_date).days + 1)
        scale_30d = Decimal("30.00") / Decimal(span_days)
        monthly_net_cash = _q2(waterfall["net_cash_flow"] * scale_30d)
        monthly_fixed_burn = _q2((waterfall["fixed_opex"] + waterfall["marketing_ad_spend"]) * scale_30d + treasury.monthly_interest_expense)

        if monthly_net_cash < ZERO:
            runway_months = float(_q2(treasury.cash_in_bank_balance / abs(monthly_net_cash)))
            burn_status = "NET_BURN"
        else:
            # Profitable / Cash-Flow Positive: also show gross OPEX coverage buffer
            runway_months = 999.0 if monthly_fixed_burn <= ZERO else float(_q2(treasury.cash_in_bank_balance / monthly_fixed_burn))
            burn_status = "CASH_FLOW_POSITIVE"

        return {
            "treasury": {
                "cash_in_bank_balance": f"{treasury.cash_in_bank_balance:.2f}",
                "monthly_interest_expense": f"{treasury.monthly_interest_expense:.2f}",
                "effective_tax_rate_pct": f"{treasury.effective_tax_rate_pct:.2f}",
            },
            "accrual_vs_cash_bridge": {
                "accrual_net_profit": f"{waterfall['net_profit']:.2f}",
                "realized_net_cash_flow": f"{waterfall['net_cash_flow']:.2f}",
                "uncollected_b2b_ar": f"{total_ar:.2f}",
                "marketplace_pending_payouts": f"{marketplace_receivable:.2f}",
                "unpaid_vendor_transporter_ap": f"{total_ap:.2f}",
            },
            "ar_aging": {k: f"{v:.2f}" for k, v in aging.items()},
            "b2b_receivables": b2b_receivables,
            "inventory_capital": {
                "total_locked_cogs": f"{inv_capital:.2f}",
                "sellable_batch_cogs": f"{sellable_inv_capital:.2f}",
                "quarantined_batch_cogs": f"{_q2(inv_capital - sellable_inv_capital):.2f}",
            },
            "payables": {
                "transporter_lr_payable": f"{lr_payables:.2f}",
                "vendor_opex_payable": f"{opex_payables:.2f}",
                "total_ap": f"{total_ap:.2f}",
            },
            "runway": {
                "burn_status": burn_status,
                "projected_monthly_net_cash": f"{monthly_net_cash:.2f}",
                "monthly_gross_burn_rate": f"{monthly_fixed_burn:.2f}",
                "runway_months": runway_months,
            },
        }


class MakerCheckerService:
    """Enforces Maker-Checker RBAC guards and bulk CSV imports for manual entries."""

    @staticmethod
    def is_admin_request(request) -> bool:
        # In session/token auth, require staff/superuser; in ERP header-role mode allow ADMIN/PROPRIETOR
        if getattr(request, "user", None) and request.user.is_authenticated:
            if request.user.is_staff or request.user.is_superuser:
                return True
            return False
        role_hdr = (request.headers.get("X-ERP-Role") or "").strip().upper()
        # Reject explicit non-admin roles; if omitted in trusted local ERP session default requires ADMIN when header sent
        if role_hdr:
            return role_hdr in ("ADMIN", "PROPRIETOR")
        return True

    @classmethod
    def import_manual_sales_csv(cls, csv_content: str, created_by=None) -> list:
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        created = []
        for row in reader:
            sku_obj = None
            if row.get("sku"):
                sku_obj = Product.objects.filter(sku=row["sku"].strip()).first()
            entry = ManualRevenueEntry.objects.create(
                sale_date=date.fromisoformat(row["sale_date"].strip()),
                reference_number=row["reference_number"].strip(),
                customer_or_store_name=row["customer_or_store_name"].strip(),
                sku=sku_obj,
                quantity=int(row.get("quantity") or 0),
                gross_amount=_q2(Decimal(row["gross_amount"].strip())),
                gst_amount=_q2(Decimal(row.get("gst_amount") or "0.00")),
                discount_amount=_q2(Decimal(row.get("discount_amount") or "0.00")),
                manual_cogs_amount=_q2(Decimal(row.get("manual_cogs_amount") or "0.00")),
                manual_freight_and_packing=_q2(Decimal(row.get("manual_freight_and_packing") or "0.00")),
                notes=row.get("notes", "Bulk CSV import"),
                approval_status=ApprovalStatus.PENDING,
                created_by=created_by,
            )
            created.append(entry)
        return created

    @classmethod
    def import_opex_csv(cls, csv_content: str, created_by=None) -> list:
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        created = []
        for row in reader:
            ch = (row.get("target_channel") or "").strip() or None
            entry = MarketingAndOpexEntry.objects.create(
                period_start_date=date.fromisoformat(row["period_start_date"].strip()),
                period_end_date=date.fromisoformat(row["period_end_date"].strip()),
                bucket=row["bucket"].strip(),
                target_channel=ch,
                amount_exclusive_gst=_q2(Decimal(row["amount_exclusive_gst"].strip())),
                gst_input_credit=_q2(Decimal(row.get("gst_input_credit") or "0.00")),
                vendor_or_platform_name=row["vendor_or_platform_name"].strip(),
                is_paid=str(row.get("is_paid", "true")).lower() in ("true", "1", "yes"),
                approval_status=ApprovalStatus.PENDING,
                created_by=created_by,
            )
            created.append(entry)
        return created

