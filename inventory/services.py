from datetime import date
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.contrib.auth.models import User
from .models import (
    Product, Batch, Location, InventoryLedger, TransactionLog, BundleMapping,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem, Invoice
)
from .exceptions import (
    InsufficientStockError, InvalidAdjustmentError, ProductNotFoundError, NegativeMarginError
)
from .tasks import sync_channel_inventory_task, generate_invoice_pdf_task


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

        # Strict FEFO: query unexpired batches ordered by expiry_date ASC, mfg_date ASC
        ledgers = list(
            InventoryLedger.objects.select_for_update()
            .select_related('batch', 'location')
            .filter(product=product, quantity__gt=0, batch__expiry_date__gte=today)
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


class WholesalerService:
    """
    Dedicated domain service managing B2B Wholesaler onboarding,
    immutable order costing, custom discount margin guards, FEFO fulfillment,
    and yield analytics.
    """

    @classmethod
    def onboard_parent(cls, name: str, gstin: str, master_email: str) -> WholesalerParent:
        if WholesalerParent.objects.filter(gstin=gstin).exists():
            raise ValueError(f"A wholesaler with GSTIN '{gstin}' is already registered.")
        if WholesalerParent.objects.filter(master_email=master_email).exists():
            raise ValueError(f"Master email '{master_email}' is already registered.")
        
        return WholesalerParent.objects.create(
            name=name.strip(),
            gstin=gstin.strip().upper(),
            master_email=master_email.strip().lower(),
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
        notes: str = None
    ) -> WholesaleOrder:
        """
        Creates a draft wholesale order, locking in base_cost and unit price (or default_b2b_price)
        immutably from the Product catalog / manual entry at the time of order intake, with GST.
        """
        if not items:
            raise ValueError("Wholesale order must contain at least one item.")

        child = WholesalerChild.objects.select_related('parent').get(id=child_id)
        if child.parent.status != 'APPROVED':
            raise ValueError("Wholesaler account is pending approval.")

        # Auto-generate PO Number if not provided
        if not po_number or not str(po_number).strip():
            year_str = timezone.now().strftime('%Y')
            prefix = child.store_id.split('-')[0].upper() if child.store_id else 'PURA'
            order_seq = WholesaleOrder.objects.filter(child_wholesaler=child).count() + 1
            po_number = f"PO-{prefix}-{year_str}-{order_seq:03d}"
        else:
            po_number = po_number.strip()

        order = WholesaleOrder.objects.create(
            parent_wholesaler=child.parent,
            child_wholesaler=child,
            po_number=po_number,
            notes=notes.strip() if notes else None,
            status='DRAFT'
        )

        subtotal = Decimal('0.00')
        total_gst = Decimal('0.00')
        total_cogs = Decimal('0.00')

        for item_data in items:
            sku = item_data['sku']
            qty = int(item_data['quantity'])
            if qty <= 0:
                raise ValueError("Item quantity must be greater than zero.")

            product = Product.objects.get(sku=sku)
            locked_cost = product.base_cost

            # If manual unit_price is provided, lock that in; else use default_b2b_price
            if 'unit_price' in item_data and item_data['unit_price'] is not None and str(item_data['unit_price']).strip() != '':
                locked_price = Decimal(str(item_data['unit_price'])).quantize(Decimal('0.01'))
            else:
                locked_price = product.default_b2b_price

            # If manual gst_percentage is provided, lock that in; else default to 18%
            if 'gst_percentage' in item_data and item_data['gst_percentage'] is not None and str(item_data['gst_percentage']).strip() != '':
                gst_pct = Decimal(str(item_data['gst_percentage'])).quantize(Decimal('0.01'))
            elif 'gst_rate' in item_data and item_data['gst_rate'] is not None and str(item_data['gst_rate']).strip() != '':
                gst_pct = Decimal(str(item_data['gst_rate'])).quantize(Decimal('0.01'))
            else:
                gst_pct = Decimal('18.00')

            line_net = locked_price * Decimal(qty)
            line_gst = (line_net * (gst_pct / Decimal('100.0'))).quantize(Decimal('0.01'))
            line_total = line_net + line_gst

            WholesaleOrderItem.objects.create(
                order=order,
                product=product,
                quantity=qty,
                locked_base_cost=locked_cost,
                locked_b2b_price=locked_price,
                gst_percentage=gst_pct,
                gst_amount=line_gst,
                line_total=line_total
            )

            subtotal += line_net
            total_gst += line_gst
            total_cogs += locked_cost * Decimal(qty)

        order.subtotal = subtotal
        order.total_gst = total_gst
        order.total_cogs = total_cogs
        order.discount_amount = Decimal('0.00')
        order.final_value = subtotal
        order.grand_total = subtotal + total_gst
        order.net_profit = subtotal - total_cogs
        order.save()

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
        order.net_profit = candidate_final_value - order.total_cogs
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
