import math
import re
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q, Count, F
from django.utils import timezone
from django.contrib.auth import get_user_model
User = get_user_model()
from .models import (
    Product, Batch, Location, InventoryLedger, TransactionLog, BundleMapping,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem, Invoice,
    WholesalerTier, DiscountMode, PricingTierSlab, PromotionalCampaign
)
from .exceptions import (
    InsufficientStockError, InvalidAdjustmentError, ProductNotFoundError, NegativeMarginError
)
from .tasks import sync_channel_inventory_task, generate_invoice_pdf_task
from core.services import AuditService
from core.models import AuditAction


class InventoryEngine:
    """
    High-performance core engine for omnichannel inventory operations.
    Enforces atomic transactions, FEFO shelf routing, bundle resolution,
    and row-level locking concurrency controls.
    """

    @classmethod
    @transaction.atomic
    def intake(
        cls,
        sku: str,
        quantity: int,
        batch_id: str,
        mfg_date: date,
        expiry_date: date,
        warehouse: str,
        aisle: str,
        row: str,
        shelf: str,
        bin: str = None,
        user=None,
        source: str = 'MANUAL'
    ) -> dict:
        if quantity <= 0:
            raise ValueError("Intake quantity must be greater than zero.")

        product = Product.objects.get(sku=sku)
        batch, _ = Batch.objects.get_or_create(
            batch_id=batch_id,
            defaults={'product': product, 'mfg_date': mfg_date, 'expiry_date': expiry_date}
        )
        location, _ = Location.objects.get_or_create(
            warehouse=warehouse, aisle=aisle, row=row, shelf=shelf, bin=bin
        )

        ledger, _ = InventoryLedger.objects.select_for_update().get_or_create(
            product=product, batch=batch, location=location, defaults={'quantity': 0}
        )
        ledger.quantity += quantity
        ledger.save(update_fields=['quantity'])

        TransactionLog.objects.create(
            product=product,
            batch=batch,
            location=location,
            quantity_change=quantity,
            transaction_type='INTAKE',
            source=source,
            user=user
        )

        # Trigger async marketplace stock synchronization
        transaction.on_commit(lambda: sync_channel_inventory_task.delay(sku=product.sku))

        return {
            "status": "SUCCESS",
            "sku": sku,
            "batch_id": batch.batch_id,
            "location_id": str(location.id),
            "quantity_added": quantity,
            "current_ledger_quantity": ledger.quantity
        }

    @classmethod
    @transaction.atomic
    def outtake(
        cls,
        sku: str,
        quantity: int,
        source: str = 'MANUAL',
        user=None
    ) -> dict:
        if quantity <= 0:
            raise ValueError("Outtake quantity must be greater than zero.")

        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            raise ProductNotFoundError(f"Product with SKU '{sku}' not found.")

        today = timezone.now().date()

        # Strict FEFO: query unexpired and non-quarantined batches ordered by expiry_date ASC, mfg_date ASC
        ledgers = list(
            InventoryLedger.objects.select_for_update()
            .select_related('batch', 'location')
            .filter(
                product=product,
                quantity__gt=0,
                batch__expiry_date__gte=today,
                batch__quarantine_status=False
            )
            .order_by('batch__expiry_date', 'batch__mfg_date', 'batch__batch_id')
        )

        total_available = sum(l.quantity for l in ledgers)
        if total_available < quantity:
            raise InsufficientStockError(
                f"Insufficient unexpired stock for SKU '{sku}'. Required: {quantity}, Available: {total_available}"
            )

        remaining_needed = quantity
        pick_directions = []

        for ledger in ledgers:
            if remaining_needed <= 0:
                break

            deduct_qty = min(ledger.quantity, remaining_needed)
            ledger.quantity -= deduct_qty
            ledger.save(update_fields=['quantity'])

            loc = ledger.location
            bin_label = f", Bin {loc.bin}" if loc.bin else ""
            shelf_guidance = f"Warehouse: {loc.warehouse} | Aisle: {loc.aisle}, Row: {loc.row}, Shelf: {loc.shelf}{bin_label}"

            pick_directions.append({
                "batch_id": ledger.batch.batch_id,
                "expiry_date": ledger.batch.expiry_date.isoformat(),
                "warehouse": loc.warehouse,
                "aisle": loc.aisle,
                "row": loc.row,
                "shelf": loc.shelf,
                "bin": loc.bin,
                "quantity_picked": deduct_qty,
                "shelf_guidance": shelf_guidance
            })

            TransactionLog.objects.create(
                product=product,
                batch=ledger.batch,
                location=loc,
                quantity_change=-deduct_qty,
                transaction_type='OUTTAKE',
                source=source,
                user=user
            )

            remaining_needed -= deduct_qty

        # Trigger async marketplace stock synchronization
        transaction.on_commit(lambda: sync_channel_inventory_task.delay(sku=product.sku))

        return {
            "status": "SUCCESS",
            "sku": sku,
            "total_deducted": quantity,
            "pick_directions": pick_directions
        }

    @classmethod
    @transaction.atomic
    def adjust(
        cls,
        sku: str,
        batch_id: str,
        location_id: str,
        quantity_change: int,
        reason_code: str,
        user=None
    ) -> dict:
        if not reason_code or not str(reason_code).strip():
            raise InvalidAdjustmentError("A valid reason_code is mandatory for manual adjustments.")
        if quantity_change == 0:
            raise InvalidAdjustmentError("quantity_change must be a non-zero integer.")

        product = Product.objects.get(sku=sku)
        batch = Batch.objects.get(batch_id=batch_id, product=product)
        location = Location.objects.get(id=location_id)

        ledger, _ = InventoryLedger.objects.select_for_update().get_or_create(
            product=product, batch=batch, location=location, defaults={'quantity': 0}
        )

        new_quantity = ledger.quantity + quantity_change
        if new_quantity < 0:
            raise InsufficientStockError(
                f"Cannot adjust inventory below zero. Current: {ledger.quantity}, Change: {quantity_change}"
            )

        ledger.quantity = new_quantity
        ledger.save(update_fields=['quantity'])

        TransactionLog.objects.create(
            product=product,
            batch=batch,
            location=location,
            quantity_change=quantity_change,
            transaction_type='ADJUST',
            source='MANUAL',
            reason_code=reason_code.strip(),
            user=user
        )

        # Trigger async marketplace stock synchronization
        transaction.on_commit(lambda: sync_channel_inventory_task.delay(sku=product.sku))

        return {
            "status": "SUCCESS",
            "sku": sku,
            "batch_id": batch.batch_id,
            "location_id": str(location.id),
            "quantity_change": quantity_change,
            "new_balance": ledger.quantity,
            "reason_code": reason_code.strip()
        }

    @classmethod
    def simulate_fefo_pick(cls, sku: str, quantity: int) -> dict:
        """
        Read-only simulation of FEFO lot allocation without deducting stock.
        Surfaces exactly which batches, warehouse coordinates, and near-expiry
        formulations will be routed before committing order dispatch.
        """
        if quantity <= 0:
            raise ValueError("Simulation quantity must be greater than zero.")

        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            raise ProductNotFoundError(f"Product with SKU '{sku}' not found.")

        today = timezone.now().date()
        ledgers = (
            InventoryLedger.objects.filter(
                product=product,
                quantity__gt=0,
                batch__expiry_date__gte=today,
                batch__quarantine_status=False
            )
            .select_related('batch', 'location')
            .order_by('batch__expiry_date', 'batch__mfg_date', 'batch__batch_id')
        )

        total_available = sum(l.quantity for l in ledgers)
        is_sufficient = total_available >= quantity

        simulated_picks = []
        remaining = quantity
        has_near_expiry = False

        for l in ledgers:
            if remaining <= 0:
                break
            pick_qty = min(l.quantity, remaining)
            is_near_exp = l.batch.is_near_expiry
            if is_near_exp:
                has_near_expiry = True

            loc = l.location
            bin_label = f", Bin {loc.bin}" if loc.bin else ""
            simulated_picks.append({
                "batch_id": l.batch.batch_id,
                "mfg_date": l.batch.mfg_date.isoformat(),
                "expiry_date": l.batch.expiry_date.isoformat(),
                "days_to_expiry": l.batch.days_to_expiry,
                "is_near_expiry": is_near_exp,
                "compliance_certificate_number": l.batch.compliance_certificate_number,
                "coa_available": bool(l.batch.coa_document),
                "warehouse": loc.warehouse,
                "location_str": f"{loc.warehouse}:{loc.aisle}-{loc.row}-{loc.shelf}{bin_label}",
                "simulated_quantity": pick_qty,
                "bin_available": l.quantity
            })
            remaining -= pick_qty

        return {
            "sku": sku,
            "product_name": product.name,
            "category": product.category,
            "skincare_line": product.skincare_line,
            "requested_quantity": quantity,
            "total_available_fefo_stock": total_available,
            "is_fulfillable": is_sufficient,
            "shortfall": max(0, quantity - total_available),
            "contains_near_expiry_batches": has_near_expiry,
            "proposed_pick_plan": simulated_picks
        }

    @classmethod
    @transaction.atomic
    def dispatch_gate_pass_fefo_outtake(
        cls,
        dispatch_reference: str,
        items: list,
        user=None,
        gate_pass_number: str = None,
        lr_number: str = None
    ) -> dict:
        """
        Executes real-time FEFO stock depletion tied directly to TMS Gate-Pass issuance
        and Lorry Receipt (LR) dispatch. Enforces strict row locks to prevent double-booking.
        """
        if not items:
            raise ValueError("Dispatch items list cannot be empty.")

        dispatch_manifest = {
            "dispatch_reference": dispatch_reference,
            "gate_pass_number": gate_pass_number or f"GP-{dispatch_reference}",
            "lr_number": lr_number,
            "timestamp": timezone.now().isoformat(),
            "items_dispatched": [],
            "total_units": 0,
            "total_cartons": Decimal('0.0'),
            "total_chargeable_weight_kg": Decimal('0.000'),
        }

        today = timezone.now().date()

        for it in items:
            sku = it['sku']
            qty = it['quantity']
            if qty <= 0:
                continue

            try:
                product = Product.objects.get(sku=sku)
            except Product.DoesNotExist:
                raise ProductNotFoundError(f"Product '{sku}' not found for gate-pass dispatch.")

            # Strict FEFO lock: unexpired & non-quarantined lots
            ledgers = list(
                InventoryLedger.objects.select_for_update()
                .select_related('batch', 'location')
                .filter(
                    product=product,
                    quantity__gt=0,
                    batch__expiry_date__gte=today,
                    batch__quarantine_status=False
                )
                .order_by('batch__expiry_date', 'batch__mfg_date', 'batch__batch_id')
            )

            avail = sum(l.quantity for l in ledgers)
            if avail < qty:
                raise InsufficientStockError(
                    f"Gate-Pass dispatch aborted for '{sku}': Insufficient FEFO sellable stock. Required: {qty}, Available: {avail}"
                )

            rem = qty
            item_picks = []

            for l in ledgers:
                if rem <= 0:
                    break
                deduct = min(l.quantity, rem)
                l.quantity -= deduct
                l.save(update_fields=['quantity'])

                loc = l.location
                item_picks.append({
                    "batch_id": l.batch.batch_id,
                    "mfg_date": l.batch.mfg_date.isoformat(),
                    "expiry_date": l.batch.expiry_date.isoformat(),
                    "compliance_certificate": l.batch.compliance_certificate_number,
                    "quantity": deduct,
                    "warehouse": loc.warehouse,
                    "location_code": f"{loc.warehouse}:{loc.aisle}-{loc.row}-{loc.shelf}"
                })

                TransactionLog.objects.create(
                    product=product,
                    batch=l.batch,
                    location=loc,
                    quantity_change=-deduct,
                    transaction_type='OUTTAKE',
                    source='GATE_PASS',
                    reason_code=f"GatePass: {dispatch_manifest['gate_pass_number']} | Ref: {dispatch_reference}",
                    user=user
                )
                rem -= deduct

            cartons = (Decimal(qty) / Decimal(product.master_carton_qty)).quantize(Decimal('0.1'))
            weight = (Decimal(qty) * product.chargeable_weight_kg).quantize(Decimal('0.001'))

            dispatch_manifest["items_dispatched"].append({
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "quantity": qty,
                "cartons": float(cartons),
                "chargeable_weight_kg": float(weight),
                "batch_picks": item_picks
            })
            dispatch_manifest["total_units"] += qty
            dispatch_manifest["total_cartons"] += cartons
            dispatch_manifest["total_chargeable_weight_kg"] += weight

            transaction.on_commit(lambda s=product.sku: sync_channel_inventory_task.delay(sku=s))

        dispatch_manifest["total_cartons"] = float(dispatch_manifest["total_cartons"])
        dispatch_manifest["total_chargeable_weight_kg"] = float(dispatch_manifest["total_chargeable_weight_kg"])

        AuditService.log(
            action=AuditAction.GATE_PASS_ISSUED,
            entity_type='DispatchGatePass',
            entity_id=dispatch_manifest['gate_pass_number'],
            actor=user,
            post_snapshot={
                "dispatch_reference": dispatch_reference,
                "total_units": dispatch_manifest["total_units"],
                "total_cartons": dispatch_manifest["total_cartons"],
                "lr_number": lr_number
            }
        )

        return dispatch_manifest

    @classmethod
    @transaction.atomic
    def set_batch_quarantine(cls, batch_id: str, quarantine: bool, reason: str, user=None) -> dict:
        """
        Toggles quarantine status of a formulation lot and logs an immutable audit event.
        Quarantined lots are immediately excluded from sellable inventory and FEFO routing.
        """
        try:
            batch = Batch.objects.select_for_update().get(batch_id=batch_id)
        except Batch.DoesNotExist:
            raise ValueError(f"Batch with ID '{batch_id}' not found.")

        old_status = batch.quarantine_status
        batch.quarantine_status = quarantine
        if reason:
            prefix = "[QUARANTINED]" if quarantine else "[RELEASED]"
            batch.formulation_notes = f"{prefix} {reason.strip()} | {batch.formulation_notes or ''}".strip()
        batch.save(update_fields=['quarantine_status', 'formulation_notes'])

        AuditService.log(
            action=AuditAction.BATCH_EXPIRY_OVERRIDE,
            entity_type='Batch',
            entity_id=batch.batch_id,
            actor=user,
            pre_snapshot={"quarantine_status": old_status},
            post_snapshot={"quarantine_status": quarantine},
            metadata={"reason": reason, "sku": batch.product_id}
        )

        # Trigger async marketplace stock synchronization because sellable stock changed
        transaction.on_commit(lambda: sync_channel_inventory_task.delay(sku=batch.product_id))

        return {
            "status": "SUCCESS",
            "batch_id": batch.batch_id,
            "product_sku": batch.product_id,
            "quarantine_status": batch.quarantine_status,
            "is_sellable_fefo": batch.is_sellable_fefo,
            "notes": batch.formulation_notes
        }

    @classmethod
    def get_batch_traceability(cls, batch_id: str) -> dict:
        """
        Full lot genealogy and warehouse distribution for regulatory cosmetic compliance.
        """
        try:
            batch = Batch.objects.select_related('product').get(batch_id=batch_id)
        except Batch.DoesNotExist:
            raise ValueError(f"Batch '{batch_id}' does not exist.")

        ledgers = InventoryLedger.objects.filter(batch=batch).select_related('location')
        locations = []
        total_qty = 0
        for l in ledgers:
            loc = l.location
            bin_str = f", Bin {loc.bin}" if loc.bin else ""
            locations.append({
                "location_id": str(loc.id),
                "warehouse": loc.warehouse,
                "shelf_code": f"{loc.warehouse}:{loc.aisle}-{loc.row}-{loc.shelf}{bin_str}",
                "quantity": l.quantity
            })
            total_qty += l.quantity

        recent_logs = (
            TransactionLog.objects.filter(batch=batch)
            .order_by('-timestamp')[:10]
            .values('id', 'timestamp', 'quantity_change', 'transaction_type', 'source', 'reason_code')
        )

        return {
            "batch_id": batch.batch_id,
            "product": {
                "sku": batch.product.sku,
                "name": batch.product.name,
                "category": batch.product.category,
                "skincare_line": batch.product.skincare_line,
                "mineral_actives": batch.product.mineral_actives,
                "packaging_format": batch.product.packaging_format,
                "hsn_code": batch.product.hsn_code,
            },
            "mfg_date": batch.mfg_date.isoformat(),
            "expiry_date": batch.expiry_date.isoformat(),
            "days_to_expiry": batch.days_to_expiry,
            "is_expired": batch.is_expired,
            "is_near_expiry": batch.is_near_expiry,
            "quarantine_status": batch.quarantine_status,
            "is_sellable_fefo": batch.is_sellable_fefo,
            "compliance_certificate_number": batch.compliance_certificate_number,
            "coa_document_url": batch.coa_document.url if batch.coa_document else None,
            "total_inventory_units": total_qty,
            "locations": locations,
            "recent_ledger_movements": list(recent_logs)
        }

    @classmethod
    @transaction.atomic
    def process_order(cls, order_id: str, source: str, items: list, user=None) -> dict:
        order_fulfillment = {
            "order_id": order_id,
            "source": source,
            "fulfilled_items": []
        }

        for item in items:
            raw_sku = item['sku']
            order_qty = item['quantity']

            bundle = BundleMapping.objects.filter(promo_sku=raw_sku).select_related('base_product').first()
            if bundle:
                base_sku = bundle.base_product.sku
                effective_qty = order_qty * bundle.quantity_multiplier
                is_bundle = True
                multiplier = bundle.quantity_multiplier
            else:
                base_sku = raw_sku
                effective_qty = order_qty
                is_bundle = False
                multiplier = 1

            outtake_res = cls.outtake(
                sku=base_sku,
                quantity=effective_qty,
                source=source,
                user=user
            )

            order_fulfillment["fulfilled_items"].append({
                "ordered_sku": raw_sku,
                "is_bundle": is_bundle,
                "quantity_multiplier": multiplier,
                "base_sku": base_sku,
                "ordered_quantity": order_qty,
                "actual_quantity_deducted": effective_qty,
                "pick_directions": outtake_res["pick_directions"]
            })

        return order_fulfillment

    @classmethod
    def get_inventory_summary(cls, sku: str) -> dict:
        product = Product.objects.get(sku=sku)
        today = timezone.now().date()

        stats = InventoryLedger.objects.filter(product=product).aggregate(
            total=Sum('quantity'),
            expired=Sum('quantity', filter=Q(batch__expiry_date__lt=today))
        )

        total_qty = stats['total'] or 0
        expired_qty = stats['expired'] or 0
        sellable_qty = max(0, total_qty - expired_qty)

        batches = []
        for l in InventoryLedger.objects.filter(product=product, quantity__gt=0).select_related('batch', 'location').order_by('batch__expiry_date'):
            loc = l.location
            bin_str = f"-{loc.bin}" if loc.bin else ""
            batches.append({
                "batch_id": l.batch.batch_id,
                "expiry_date": l.batch.expiry_date.isoformat(),
                "mfg_date": l.batch.mfg_date.isoformat(),
                "is_expired": l.batch.expiry_date < today,
                "quantity": l.quantity,
                "location": {
                    "id": str(loc.id),
                    "warehouse": loc.warehouse,
                    "aisle": loc.aisle,
                    "row": loc.row,
                    "shelf": loc.shelf,
                    "bin": loc.bin,
                    "display": f"{loc.warehouse}:{loc.aisle}-{loc.row}-{loc.shelf}{bin_str}"
                }
            })

        return {
            "sku": product.sku,
            "product_name": product.name,
            "base_price": str(product.base_price),
            "base_cost": str(product.base_cost),
            "default_b2b_price": str(product.default_b2b_price),
            "total_quantity": total_qty,
            "expired_quantity": expired_qty,
            "sellable_quantity": sellable_qty,
            "batches": batches
        }


class WholesalePricingEngine:
    """
    Dynamic Tiered Margin Matrix, Volume Slab Engine & Pre-Dispatch Profitability Simulator.
    Calculates wholesale pricing structures across MRP, PTR, and PTS slabs,
    evaluates formulation base costs (COGS), variable overheads (freight & packaging),
    applies promotional campaigns & complimentary tester bundles, and strictly
    enforces NegativeMarginError floor protection.
    """

    @staticmethod
    def validate_gstin(gstin: str) -> bool:
        if not gstin or not isinstance(gstin, str):
            return False
        pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
        return bool(re.match(pattern, gstin.strip().upper()))

    @classmethod
    def resolve_pricing_slab(cls, product: Product, tier: str, cartons: int) -> tuple[object, Decimal, Decimal, Decimal | None]:
        """
        Resolves applicable PTR discount %, PTS discount %, or flat unit price override.
        Checks product-specific slab first; falls back to global tier slab; falls back to default margins.
        """
        # 1. Product-specific slab
        slab = PricingTierSlab.objects.filter(
            product=product,
            tier=tier,
            is_active=True,
            min_cartons__lte=cartons
        ).filter(
            Q(max_cartons__gte=cartons) | Q(max_cartons__isnull=True)
        ).order_by('-min_cartons').first()

        # 2. Global category/tier slab
        if not slab:
            slab = PricingTierSlab.objects.filter(
                product__isnull=True,
                tier=tier,
                is_active=True,
                min_cartons__lte=cartons
            ).filter(
                Q(max_cartons__gte=cartons) | Q(max_cartons__isnull=True)
            ).order_by('-min_cartons').first()

        if slab:
            return slab, slab.ptr_discount_pct, slab.pts_discount_pct, slab.custom_unit_price

        # 3. Default fallback margins by tier
        tier_fallbacks = {
            WholesalerTier.RETAILER: (Decimal('25.00'), Decimal('25.00'), None),
            WholesalerTier.STOCKIST: (Decimal('25.00'), Decimal('35.00'), None),
            WholesalerTier.SUPER_STOCKIST: (Decimal('25.00'), Decimal('42.00'), None),
            WholesalerTier.INSTITUTIONAL: (Decimal('30.00'), Decimal('30.00'), None),
        }
        ptr_d, pts_d, flat_p = tier_fallbacks.get(tier, (Decimal('25.00'), Decimal('25.00'), None))
        return None, ptr_d, pts_d, flat_p

    @classmethod
    def simulate_order_profitability(
        cls,
        items: list,
        parent: WholesalerParent = None,
        parent_id: int = None,
        campaign_code: str = None,
        estimated_freight: Decimal = Decimal('0.00'),
        packaging_cost: Decimal = Decimal('0.00'),
    ) -> dict:
        """
        Real-time simulation evaluating formulation base cost (COGS), variable overheads
        (freight, packaging), volume-scaled dealer discounts, and promotional markdowns.
        Returns Gross Margin, Net Realization, and Margin Yield %.
        Strictly prevents quotations yielding negative margins below base_cost floor (NegativeMarginError).
        """
        if not items:
            raise ValueError("Simulation requires at least one order item.")

        if not parent and parent_id:
            parent = WholesalerParent.objects.get(id=parent_id)

        tier = parent.tier if parent else WholesalerTier.RETAILER
        estimated_freight = Decimal(str(estimated_freight)).quantize(Decimal('0.01'))
        packaging_cost = Decimal(str(packaging_cost)).quantize(Decimal('0.01'))

        # Fetch and validate promotional campaign if specified
        campaign = None
        if campaign_code and str(campaign_code).strip():
            try:
                campaign = PromotionalCampaign.objects.prefetch_related('applicable_skus').get(
                    campaign_code=str(campaign_code).strip()
                )
                if not campaign.is_currently_valid:
                    raise ValueError(f"Promotional campaign '{campaign_code}' is inactive, expired, or over budget.")
            except PromotionalCampaign.DoesNotExist:
                raise ValueError(f"Promotional campaign '{campaign_code}' not found.")

        simulated_items = []
        subtotal = Decimal('0.00')
        total_product_cogs = Decimal('0.00')
        total_gst = Decimal('0.00')
        total_units = 0
        total_cartons = 0

        # Pass 1: Line item calculation
        for item in items:
            sku = item['sku']
            qty = int(item['quantity'])
            if qty <= 0:
                raise ValueError(f"Quantity for SKU '{sku}' must be greater than zero.")

            try:
                product = Product.objects.get(sku=sku)
            except Product.DoesNotExist:
                raise ProductNotFoundError(f"Product '{sku}' not found.")

            mrp = product.base_price
            base_cost = product.base_cost
            carton_size = max(1, product.master_carton_qty)
            cartons = math.ceil(qty / carton_size)

            # Resolve volume slab
            slab, ptr_pct, pts_pct, flat_override = cls.resolve_pricing_slab(product, tier, cartons)

            if 'unit_price' in item and item['unit_price'] is not None and str(item['unit_price']).strip() != '':
                unit_price = Decimal(str(item['unit_price'])).quantize(Decimal('0.01'))
                applied_discount_pct = (
                    ((mrp - unit_price) / mrp * Decimal('100.00')).quantize(Decimal('0.01'))
                    if mrp > Decimal('0.00') else Decimal('0.00')
                )
            elif flat_override is not None:
                unit_price = flat_override.quantize(Decimal('0.01'))
                applied_discount_pct = (
                    ((mrp - unit_price) / mrp * Decimal('100.00')).quantize(Decimal('0.01'))
                    if mrp > Decimal('0.00') else Decimal('0.00')
                )
            elif slab is not None:
                applied_discount_pct = ptr_pct if tier == WholesalerTier.RETAILER else pts_pct
                unit_price = (mrp * (Decimal('100.00') - applied_discount_pct) / Decimal('100.00')).quantize(Decimal('0.01'))
            elif product.default_b2b_price > Decimal('0.00'):
                # When no volume slab is explicitly configured, use product's default B2B base price
                if tier in [WholesalerTier.STOCKIST, WholesalerTier.SUPER_STOCKIST]:
                    applied_discount_pct = pts_pct
                    unit_price = (mrp * (Decimal('100.00') - applied_discount_pct) / Decimal('100.00')).quantize(Decimal('0.01'))
                else:
                    unit_price = product.default_b2b_price
                    applied_discount_pct = (
                        ((mrp - unit_price) / mrp * Decimal('100.00')).quantize(Decimal('0.01'))
                        if mrp > Decimal('0.00') else Decimal('0.00')
                    )
            else:
                applied_discount_pct = ptr_pct if tier == WholesalerTier.RETAILER else pts_pct
                unit_price = (mrp * (Decimal('100.00') - applied_discount_pct) / Decimal('100.00')).quantize(Decimal('0.01'))

            # GST rate
            if 'gst_percentage' in item and item['gst_percentage'] is not None and str(item['gst_percentage']).strip() != '':
                gst_pct = Decimal(str(item['gst_percentage'])).quantize(Decimal('0.01'))
            elif 'gst_rate' in item and item['gst_rate'] is not None and str(item['gst_rate']).strip() != '':
                gst_pct = Decimal(str(item['gst_rate'])).quantize(Decimal('0.01'))
            else:
                gst_pct = Decimal('18.00')

            line_gross = (unit_price * Decimal(qty)).quantize(Decimal('0.01'))
            line_gst = (line_gross * (gst_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            line_total = line_gross + line_gst
            line_cogs = (base_cost * Decimal(qty)).quantize(Decimal('0.01'))

            simulated_items.append({
                'sku': product.sku,
                'name': product.name,
                'quantity': qty,
                'cartons': cartons,
                'mrp_unit': str(mrp),
                'unit_price': str(unit_price),
                'base_cost_unit': str(base_cost),
                'applied_discount_pct': str(applied_discount_pct),
                'gst_percentage': str(gst_pct),
                'line_gross': str(line_gross),
                'line_gst': str(line_gst),
                'line_total': str(line_total),
                'line_cogs': str(line_cogs),
                'product_obj': product,
                '_raw_line_gross': line_gross,
                '_raw_line_cogs': line_cogs,
                '_raw_line_gst': line_gst,
            })

            subtotal += line_gross
            total_product_cogs += line_cogs
            total_gst += line_gst
            total_units += qty
            total_cartons += cartons

        # Pass 2: Promotional campaign application
        applied_promo_discount = Decimal('0.00')
        tester_bundle_info = {}
        tester_cogs = Decimal('0.00')

        if campaign:
            applicable_skus = set(campaign.applicable_skus.values_list('sku', flat=True))
            if applicable_skus:
                eligible_subtotal = sum(
                    item['_raw_line_gross'] for item in simulated_items if item['sku'] in applicable_skus
                )
            else:
                eligible_subtotal = subtotal

            if campaign.discount_pct > Decimal('0.00'):
                applied_promo_discount += (eligible_subtotal * (campaign.discount_pct / Decimal('100.00'))).quantize(Decimal('0.01'))

            if campaign.flat_discount_amount > Decimal('0.00'):
                applied_promo_discount += campaign.flat_discount_amount.quantize(Decimal('0.01'))

            # Check remaining campaign budget
            if campaign.allocated_budget > Decimal('0.00'):
                remaining_budget = max(Decimal('0.00'), campaign.allocated_budget - campaign.consumed_discount_total)
                applied_promo_discount = min(applied_promo_discount, remaining_budget)

            # Complimentary tester allocation (does not distort commercial invoice, but accounted in formulation COGS)
            if campaign.complimentary_tester_sku and campaign.tester_quantity_per_order > 0:
                tester_sku = campaign.complimentary_tester_sku
                tester_qty = campaign.tester_quantity_per_order
                tester_cogs = (tester_sku.base_cost * Decimal(tester_qty)).quantize(Decimal('0.01'))
                tester_bundle_info = {
                    'sku': tester_sku.sku,
                    'name': tester_sku.name,
                    'quantity': tester_qty,
                    'unit_cogs': str(tester_sku.base_cost),
                    'total_tester_cogs': str(tester_cogs),
                    'charge_to_customer': '0.00'
                }

        final_value = (subtotal - applied_promo_discount).quantize(Decimal('0.01'))
        grand_total = (final_value + total_gst).quantize(Decimal('0.01'))
        total_order_cogs = (total_product_cogs + tester_cogs).quantize(Decimal('0.01'))
        variable_overheads = (estimated_freight + packaging_cost).quantize(Decimal('0.01'))
        net_realization = (final_value - variable_overheads).quantize(Decimal('0.01'))
        gross_margin = (final_value - total_order_cogs).quantize(Decimal('0.01'))
        gross_margin_pct = (
            ((gross_margin / final_value) * Decimal('100.00')).quantize(Decimal('0.02'))
            if final_value > Decimal('0.00') else Decimal('0.00')
        )
        net_profit = (net_realization - total_order_cogs).quantize(Decimal('0.01'))
        net_margin_yield_pct = (
            ((net_profit / final_value) * Decimal('100.00')).quantize(Decimal('0.02'))
            if final_value > Decimal('0.00') else Decimal('0.00')
        )

        # STRICT PRICE FLOOR PROTECTION: Prevent negative margin yield
        if final_value < total_order_cogs or net_realization < total_order_cogs or net_profit < Decimal('0.00'):
            max_allowable_discount = max(Decimal('0.00'), subtotal - total_order_cogs - variable_overheads)
            raise NegativeMarginError(
                f"Quotation yields negative margin (Net Profit: -₹{abs(net_profit):.2f}, Yield: {net_margin_yield_pct}%). "
                f"Net realization ₹{net_realization:.2f} is below total formulation COGS floor ₹{total_order_cogs:.2f}. "
                f"Maximum allowable promotional/trade discount is ₹{max_allowable_discount:.2f}."
            )

        # Clean private helper keys before returning
        for item in simulated_items:
            item.pop('product_obj', None)
            item.pop('_raw_line_gross', None)
            item.pop('_raw_line_cogs', None)
            item.pop('_raw_line_gst', None)

        return {
            'status': 'APPROVED_PROFITABLE',
            'tier': tier,
            'total_units': total_units,
            'total_cartons': total_cartons,
            'items': simulated_items,
            'subtotal': str(subtotal),
            'promotional_discount': str(applied_promo_discount),
            'final_value': str(final_value),
            'total_gst': str(total_gst),
            'grand_total': str(grand_total),
            'total_cogs': str(total_order_cogs),
            'product_cogs': str(total_product_cogs),
            'tester_cogs': str(tester_cogs),
            'estimated_freight': str(estimated_freight),
            'packaging_cost': str(packaging_cost),
            'variable_overheads': str(variable_overheads),
            'net_realization': str(net_realization),
            'gross_margin': str(gross_margin),
            'gross_margin_pct': str(gross_margin_pct),
            'net_profit': str(net_profit),
            'net_margin_yield_pct': str(net_margin_yield_pct),
            'campaign_applied': campaign.campaign_code if campaign else None,
            'tester_bundle': tester_bundle_info if tester_bundle_info else None,
        }


class WholesalerService:
    """
    Dedicated domain service managing B2B Wholesaler onboarding,
    tier profiles, volume pricing, pre-dispatch simulation, FEFO fulfillment,
    and yield analytics.
    """

    @classmethod
    def onboard_parent(
        cls,
        name: str,
        gstin: str,
        master_email: str,
        tier: str = WholesalerTier.RETAILER,
        trade_license_number: str = None,
        cosmetic_license_number: str = None,
        billing_address: str = None,
        shipping_address: str = None,
        city: str = None,
        state: str = None,
        pincode: str = None,
        assigned_credit_limit: Decimal = Decimal('0.00'),
        credit_period_days: int = 30,
        discount_mode: str = DiscountMode.PERCENTAGE,
        show_discount_on_invoice: bool = True
    ) -> WholesalerParent:
        gstin_clean = gstin.strip().upper()
        if not WholesalePricingEngine.validate_gstin(gstin_clean):
            raise ValueError(f"Invalid Indian GSTIN '{gstin_clean}'. Must be exactly 15 characters matching statutory GSTIN format.")

        if WholesalerParent.objects.filter(gstin=gstin_clean).exists():
            raise ValueError(f"A wholesaler with GSTIN '{gstin_clean}' is already registered.")
        if WholesalerParent.objects.filter(master_email=master_email.strip().lower()).exists():
            raise ValueError(f"Master email '{master_email}' is already registered.")
        
        return WholesalerParent.objects.create(
            name=name.strip(),
            tier=tier,
            trade_license_number=trade_license_number.strip() if trade_license_number else None,
            cosmetic_license_number=cosmetic_license_number.strip() if cosmetic_license_number else None,
            gstin=gstin_clean,
            master_email=master_email.strip().lower(),
            billing_address=billing_address.strip() if billing_address else None,
            shipping_address=shipping_address.strip() if shipping_address else None,
            city=city.strip() if city else None,
            state=state.strip() if state else None,
            pincode=pincode.strip() if pincode else None,
            assigned_credit_limit=Decimal(str(assigned_credit_limit)),
            credit_period_days=int(credit_period_days),
            discount_mode=discount_mode,
            show_discount_on_invoice=show_discount_on_invoice,
            status='PENDING'
        )

    @classmethod
    def approve_parent(cls, parent_id: int) -> WholesalerParent:
        parent = WholesalerParent.objects.get(id=parent_id)
        parent.status = 'APPROVED'
        parent.save(update_fields=['status'])
        return parent

    @classmethod
    @transaction.atomic
    def create_child_account(
        cls,
        parent_id: int,
        branch_name: str,
        store_id: str,
        shipping_address: str,
        contact_person: str,
        username: str,
        password: str = None
    ) -> WholesalerChild:
        parent = WholesalerParent.objects.get(id=parent_id)
        if parent.status != 'APPROVED':
            raise ValueError("Cannot spawn child branches for an unapproved master wholesaler.")

        if WholesalerChild.objects.filter(store_id=store_id).exists():
            raise ValueError(f"Store ID '{store_id}' already exists.")

        user, created = User.objects.get_or_create(username=username.strip())
        if password:
            user.set_password(password)
        else:
            user.set_password("Wholesale@123")
        user.save()

        child = WholesalerChild.objects.create(
            parent=parent,
            user=user,
            branch_name=branch_name.strip(),
            store_id=store_id.strip().upper(),
            shipping_address=shipping_address.strip(),
            contact_person=contact_person.strip()
        )
        return child

    @classmethod
    @transaction.atomic
    def create_draft_order(
        cls,
        child_id: int,
        items: list,
        po_number: str = None,
        notes: str = None,
        campaign_code: str = None,
        estimated_freight: Decimal = Decimal('0.00'),
        packaging_cost: Decimal = Decimal('0.00')
    ) -> WholesaleOrder:
        """
        Creates a draft wholesale order, evaluating tiered volume slabs, promotional markdowns,
        and tester bundle allocations via WholesalePricingEngine with strict NegativeMarginError guards.
        """
        if not items:
            raise ValueError("Wholesale order must contain at least one item.")

        child = WholesalerChild.objects.select_related('parent').get(id=child_id)
        if child.parent.status != 'APPROVED':
            raise ValueError("Wholesaler account is pending approval.")

        # Run pre-dispatch profitability simulation and price floor protection
        simulation = WholesalePricingEngine.simulate_order_profitability(
            items=items,
            parent=child.parent,
            campaign_code=campaign_code,
            estimated_freight=estimated_freight,
            packaging_cost=packaging_cost
        )

        # Auto-generate PO Number if not provided
        if not po_number or not str(po_number).strip():
            year_str = timezone.now().strftime('%Y')
            prefix = child.store_id.split('-')[0].upper() if child.store_id else 'PURA'
            order_seq = WholesaleOrder.objects.filter(child_wholesaler=child).count() + 1
            po_number = f"PO-{prefix}-{year_str}-{order_seq:03d}"
        else:
            po_number = po_number.strip()

        campaign_obj = None
        if campaign_code and str(campaign_code).strip():
            campaign_obj = PromotionalCampaign.objects.filter(campaign_code=str(campaign_code).strip()).first()

        order = WholesaleOrder.objects.create(
            parent_wholesaler=child.parent,
            child_wholesaler=child,
            campaign=campaign_obj,
            po_number=po_number,
            notes=notes.strip() if notes else None,
            status='DRAFT',
            subtotal=Decimal(simulation['subtotal']),
            discount_amount=Decimal(simulation['promotional_discount']),
            final_value=Decimal(simulation['final_value']),
            total_gst=Decimal(simulation['total_gst']),
            grand_total=Decimal(simulation['grand_total']),
            total_cogs=Decimal(simulation['total_cogs']),
            estimated_freight=Decimal(simulation['estimated_freight']),
            packaging_cost=Decimal(simulation['packaging_cost']),
            gross_margin=Decimal(simulation['gross_margin']),
            net_profit=Decimal(simulation['net_profit']),
            net_margin_yield_pct=Decimal(simulation['net_margin_yield_pct']),
            tester_bundle_info=simulation.get('tester_bundle') or {}
        )

        # Create line items with locked historical costs & slab discounts
        for item_sim in simulation['items']:
            product = Product.objects.get(sku=item_sim['sku'])
            WholesaleOrderItem.objects.create(
                order=order,
                product=product,
                quantity=item_sim['quantity'],
                mrp_unit=Decimal(item_sim['mrp_unit']),
                slab_discount_pct=Decimal(item_sim['applied_discount_pct']),
                promotional_discount_amount=Decimal('0.00'),
                locked_base_cost=Decimal(item_sim['base_cost_unit']),
                locked_b2b_price=Decimal(item_sim['unit_price']),
                gst_percentage=Decimal(item_sim['gst_percentage']),
                gst_amount=Decimal(item_sim['line_gst']),
                line_total=Decimal(item_sim['line_total'])
            )

        # Record consumed discount against campaign budget
        if campaign_obj and Decimal(simulation['promotional_discount']) > Decimal('0.00'):
            campaign_obj.consumed_discount_total += Decimal(simulation['promotional_discount'])
            campaign_obj.save(update_fields=['consumed_discount_total'])

        return order

    @classmethod
    @transaction.atomic
    def apply_discount(cls, order_id: str, discount_type: str, discount_value: float) -> WholesaleOrder:
        """
        Applies a flat or percentage discount to a wholesale order while enforcing
        the absolute cost floor. Prevents discounts that yield negative net margins.
        """
        order = WholesaleOrder.objects.select_for_update().get(id=order_id)
        if order.status not in ['DRAFT', 'DISCOUNT_APPLIED']:
            raise ValueError(f"Cannot apply discount to an order with status '{order.status}'.")

        d_val = Decimal(str(discount_value))
        if discount_type == 'PERCENTAGE':
            if d_val < 0 or d_val > 100:
                raise ValueError("Percentage discount must be between 0% and 100%.")
            discount_amount = (order.subtotal * (d_val / Decimal('100.0'))).quantize(Decimal('0.01'))
        elif discount_type == 'FLAT':
            if d_val < 0:
                raise ValueError("Flat discount amount cannot be negative.")
            discount_amount = d_val.quantize(Decimal('0.01'))
        else:
            raise ValueError("discount_type must be either 'FLAT' or 'PERCENTAGE'.")

        candidate_final_value = order.subtotal - discount_amount

        # Margin protection: Ensure price does not breach the total COGS floor
        if candidate_final_value < order.total_cogs:
            max_permissible_discount = max(Decimal('0.00'), order.subtotal - order.total_cogs)
            raise NegativeMarginError(
                f"Discount of ₹{discount_amount:.2f} breaches the absolute cost floor (Total COGS: ₹{order.total_cogs:.2f}). "
                f"Maximum allowable discount is ₹{max_permissible_discount:.2f} to prevent negative margins."
            )

        order.discount_amount = discount_amount
        order.final_value = candidate_final_value
        order.grand_total = candidate_final_value + order.total_gst
        variable_overheads = order.estimated_freight + order.packaging_cost
        order.gross_margin = candidate_final_value - order.total_cogs
        order.net_profit = candidate_final_value - variable_overheads - order.total_cogs
        order.net_margin_yield_pct = (
            ((order.net_profit / candidate_final_value) * Decimal('100.00')).quantize(Decimal('0.02'))
            if candidate_final_value > Decimal('0.00') else Decimal('0.00')
        )
        order.status = 'DISCOUNT_APPLIED'
        order.save()

        return order

    @classmethod
    @transaction.atomic
    def confirm_order(cls, order_id: str, user=None) -> dict:
        """
        Confirms a wholesale order, executes FEFO physical stock deduction
        via InventoryEngine.outtake, marks order CONFIRMED, and triggers
        the async Celery invoice PDF generation task.
        """
        order = WholesaleOrder.objects.select_for_update().get(id=order_id)
        if order.status not in ['DRAFT', 'DISCOUNT_APPLIED']:
            raise ValueError(f"Order cannot be confirmed from status '{order.status}'.")

        pick_results = []

        # Deduct stock for each item using core IMS FEFO engine
        for item in order.items.select_related('product').all():
            outtake_res = InventoryEngine.outtake(
                sku=item.product.sku,
                quantity=item.quantity,
                source='WHOLESALE',
                user=user
            )
            pick_results.append({
                "sku": item.product.sku,
                "quantity": item.quantity,
                "pick_directions": outtake_res["pick_directions"]
            })

        order.status = 'CONFIRMED'
        order.save(update_fields=['status', 'updated_at'])

        # Asynchronously generate PDF invoice via Celery on commit
        transaction.on_commit(lambda: generate_invoice_pdf_task.delay(order_id=str(order.id)))

        return {
            "status": "SUCCESS",
            "order_id": str(order.id),
            "order_status": order.status,
            "final_value": str(order.final_value),
            "net_profit": str(order.net_profit),
            "pick_results": pick_results
        }

    @classmethod
    def get_analytics(cls, parent_id: int = None) -> dict:
        """
        Master & Individual Wholesaler Dashboard analytics.
        Calculates exact margin yields, revenue totals, and COGS baselines.
        """
        if parent_id:
            parent = WholesalerParent.objects.get(id=parent_id)
            orders = WholesaleOrder.objects.filter(
                parent_wholesaler=parent,
                status__in=['CONFIRMED', 'FULFILLED']
            )
            stats = orders.aggregate(
                rev=Sum('final_value'),
                cogs=Sum('total_cogs'),
                profit=Sum('net_profit'),
                count=Count('id')
            )
            rev = stats['rev'] or Decimal('0.00')
            cogs = stats['cogs'] or Decimal('0.00')
            profit = stats['profit'] or Decimal('0.00')
            margin_yield = ((profit / rev) * Decimal('100.0')).quantize(Decimal('0.01')) if rev > 0 else Decimal('0.00')

            return {
                "parent_id": parent.id,
                "name": parent.name,
                "gstin": parent.gstin,
                "status": parent.status,
                "total_orders": stats['count'],
                "total_revenue": f"{rev:.2f}",
                "total_cogs": f"{cogs:.2f}",
                "net_profit": f"{profit:.2f}",
                "margin_yield_percentage": float(margin_yield)
            }
        else:
            active_wholesalers = WholesalerParent.objects.filter(status='APPROVED').count()
            pending_wholesalers = WholesalerParent.objects.filter(status='PENDING').count()
            orders = WholesaleOrder.objects.filter(status__in=['CONFIRMED', 'FULFILLED'])
            stats = orders.aggregate(
                rev=Sum('final_value'),
                cogs=Sum('total_cogs'),
                profit=Sum('net_profit'),
                count=Count('id')
            )
            total_rev = stats['rev'] or Decimal('0.00')
            total_cogs = stats['cogs'] or Decimal('0.00')
            total_profit = stats['profit'] or Decimal('0.00')
            system_margin_pct = ((total_profit / total_rev) * Decimal('100.0')).quantize(Decimal('0.01')) if total_rev > 0 else Decimal('0.00')

            # Per-parent breakdown
            parents = WholesalerParent.objects.all().order_by('-created_at')
            parent_analytics = []
            for p in parents:
                p_orders = WholesaleOrder.objects.filter(parent_wholesaler=p, status__in=['CONFIRMED', 'FULFILLED'])
                p_stats = p_orders.aggregate(rev=Sum('final_value'), profit=Sum('net_profit'), count=Count('id'))
                p_rev = p_stats['rev'] or Decimal('0.00')
                p_profit = p_stats['profit'] or Decimal('0.00')
                p_yield = ((p_profit / p_rev) * Decimal('100.0')).quantize(Decimal('0.01')) if p_rev > 0 else Decimal('0.00')
                parent_analytics.append({
                    "id": p.id,
                    "name": p.name,
                    "gstin": p.gstin,
                    "status": p.status,
                    "orders_count": p_stats['count'],
                    "revenue": f"{p_rev:.2f}",
                    "net_profit": f"{p_profit:.2f}",
                    "margin_yield_percentage": float(p_yield)
                })

            return {
                "active_wholesalers_count": active_wholesalers,
                "pending_wholesalers_count": pending_wholesalers,
                "total_orders_count": stats['count'],
                "total_wholesale_revenue": f"{total_rev:.2f}",
                "total_wholesale_cogs": f"{total_cogs:.2f}",
                "total_wholesale_profit": f"{total_profit:.2f}",
                "system_net_profit_margin_percentage": float(system_margin_pct),
                "wholesalers": parent_analytics
            }
