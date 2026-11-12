import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

ZERO = Decimal("0.00")


def _q2(val: Decimal) -> Decimal:
    return Decimal(val or ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SalesChannel(models.TextChoices):
    B2B_WHOLESALE = "B2B_WHOLESALE", "B2B Wholesaler & Stockist ERP"
    SHOPIFY_D2C = "SHOPIFY_D2C", "Shopify D2C (purastone.co)"
    AMAZON = "AMAZON", "Amazon India Marketplace"
    FLIPKART = "FLIPKART", "Flipkart Marketplace"
    MANUAL_OFFLINE = "MANUAL_OFFLINE", "Manual / Offline Retail & Exhibitions"


class ReconciliationStatus(models.TextChoices):
    PROVISIONAL = "PROVISIONAL", "Provisional (Estimated Fees/Freight)"
    RECONCILED = "RECONCILED", "Reconciled (Verified Settlement/POD)"
    DISPUTED = "DISPUTED", "Disputed (Fee Overcharge / Missing RTO)"


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Admin Approval"
    APPROVED = "APPROVED", "Approved & Posted to P&L"
    REJECTED = "REJECTED", "Rejected"


class ChannelSkuMapping(models.Model):
    """Maps internal Pura Stone Skincare SKUs to external marketplace identifiers."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    internal_sku = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="channel_mappings",
    )
    channel = models.CharField(max_length=24, choices=SalesChannel.choices)
    external_product_id = models.CharField(
        max_length=128,
        help_text="Shopify Variant ID, Amazon ASIN, or Flipkart FSN",
    )
    external_sku_code = models.CharField(max_length=128)
    default_platform_commission_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO
    )
    default_packaging_cost_per_unit = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("18.00")
    )
    default_inward_freight_per_unit = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("8.00")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "fin_channel_sku_mapping"
        unique_together = ("channel", "external_product_id")
        indexes = [
            models.Index(fields=["channel", "external_sku_code"]),
        ]

    def __str__(self):
        return f"{self.channel}: {self.external_sku_code} -> {self.internal_sku_id}"


class LorryReceipt(models.Model):
    """
    TMS Lorry Receipt & Proof of Delivery (POD) bridge for B2B freight,
    ancillary packaging, transporter AP payables, and transit damage notations.
    """
    FREIGHT_MODES = [
        ("PAID_PREPAID", "Paid / Prepaid by Purastone"),
        ("TO_PAY", "To Pay (Borne by Retailer)"),
    ]
    POD_STATUSES = [
        ("PENDING", "In Transit / Awaiting POD"),
        ("CLEAN", "Delivered Clean (POD Verified)"),
        ("DAMAGED", "Delivered with Breakage / Shortage"),
    ]
    AP_STATUSES = [
        ("PENDING", "Payable Pending"),
        ("PAID", "Settled to Transporter"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lr_number = models.CharField(max_length=64, unique=True)
    wholesale_order = models.ForeignKey(
        "inventory.WholesaleOrder",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lorry_receipts",
    )
    transporter_name = models.CharField(max_length=128)
    freight_mode = models.CharField(max_length=16, choices=FREIGHT_MODES, default="PAID_PREPAID")
    freight_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    ancillary_packaging_cost = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    transporter_payable_status = models.CharField(max_length=16, choices=AP_STATUSES, default="PENDING")
    payable_due_date = models.DateField(null=True, blank=True)

    pod_status = models.CharField(max_length=16, choices=POD_STATUSES, default="PENDING")
    pod_damage_units = models.PositiveIntegerField(default=0)
    pod_damage_cost = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    pod_notes = models.TextField(blank=True, default="")
    pod_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fin_lorry_receipt"
        ordering = ["-created_at"]

    def __str__(self):
        return f"LR {self.lr_number} ({self.transporter_name}) [{self.pod_status}]"


class BatchExpiryWriteOff(models.Model):
    """Records physical FEFO expired / QC rejected formulation batch write-offs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        "inventory.Batch",
        on_delete=models.PROTECT,
        related_name="expiry_writeoffs",
    )
    writeoff_date = models.DateField(default=timezone.now, db_index=True)
    units_written_off = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_writeoff_value = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fin_batch_expiry_writeoff"
        ordering = ["-writeoff_date", "-created_at"]

    def save(self, *args, **kwargs):
        self.total_writeoff_value = _q2(Decimal(self.units_written_off) * Decimal(self.unit_cost))
        super().save(*args, **kwargs)


class FactOrderUnitEconomics(models.Model):
    """
    Single source of truth for per-order GMV, Net Revenue, CM1, and CM2
    across B2B Wholesale, Shopify, Amazon, Flipkart, and Manual Offline sales.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_date = models.DateField(db_index=True)
    channel = models.CharField(
        max_length=24, choices=SalesChannel.choices, db_index=True
    )
    external_order_ref = models.CharField(
        max_length=128,
        help_text="B2B Invoice #, Shopify Order #, Amazon Order ID, or Manual Ref",
    )
    reconciliation_status = models.CharField(
        max_length=16,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PROVISIONAL,
        db_index=True,
    )

    # Links to internal B2B ERP & TMS entities
    b2b_retailer = models.ForeignKey(
        "inventory.WholesalerParent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_economics",
    )
    b2b_branch = models.ForeignKey(
        "inventory.WholesalerChild",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_economics",
    )
    wholesale_order = models.OneToOneField(
        "inventory.WholesaleOrder",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unit_economics",
    )
    lorry_receipt = models.ForeignKey(
        LorryReceipt,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_economics",
    )
    primary_sku = models.ForeignKey(
        "inventory.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_order_economics",
    )

    # --- TIER 1 & 2: TOP-LINE & NET REVENUE ---
    gross_sales_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    gst_tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discounts_and_rebates = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    returns_and_rto_reversal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    net_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    # --- TIER 3: DIRECT COGS & CM1 (PRODUCT MARGIN) ---
    batch_formulation_cogs = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    primary_packaging_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    inward_freight_overhead = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total_direct_cogs = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    cm1_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    cm1_margin_pct = models.DecimalField(max_digits=7, decimal_places=2, default=ZERO)

    # --- TIER 4: FULFILLMENT, CHANNEL FEES & CM2 (OPERATIONAL MARGIN) ---
    platform_commission_fees = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    payment_gateway_fees = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    outbound_freight_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        help_text="Prepaid B2B LR freight or D2C forward shipping charge",
    )
    rto_reverse_freight_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    master_carton_and_pick_pack = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    transit_breakage_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total_direct_fulfillment_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    cm2_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    cm2_margin_pct = models.DecimalField(max_digits=7, decimal_places=2, default=ZERO)

    # --- SETTLEMENT RECONCILIATION & WORKING CAPITAL TRACKING ---
    expected_payout_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    actual_settled_payout = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discrepancy_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discrepancy_reason = models.CharField(max_length=255, blank=True, default="")
    is_rto = models.BooleanField(default=False, db_index=True)
    rto_inventory_returned = models.BooleanField(default=True)
    settlement_utr = models.CharField(max_length=128, blank=True, default="")
    settled_at = models.DateTimeField(null=True, blank=True)

    # AR / Working Capital Tracking
    payment_due_date = models.DateField(null=True, blank=True, db_index=True)
    amount_collected = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fin_fact_order_unit_economics"
        unique_together = ("channel", "external_order_ref")
        indexes = [
            models.Index(fields=["order_date", "channel"]),
            models.Index(fields=["reconciliation_status", "order_date"]),
        ]

    def recalculate_waterfall(self) -> None:
        """Deterministically computes Net Revenue, CM1, and CM2 in exact Decimal arithmetic."""
        self.net_revenue = _q2(
            Decimal(self.gross_sales_gmv)
            - Decimal(self.gst_tax_amount)
            - Decimal(self.discounts_and_rebates)
            - Decimal(self.returns_and_rto_reversal)
        )
        self.total_direct_cogs = _q2(
            Decimal(self.batch_formulation_cogs)
            + Decimal(self.primary_packaging_cost)
            + Decimal(self.inward_freight_overhead)
        )
        self.cm1_amount = _q2(self.net_revenue - self.total_direct_cogs)

        self.total_direct_fulfillment_cost = _q2(
            Decimal(self.platform_commission_fees)
            + Decimal(self.payment_gateway_fees)
            + Decimal(self.outbound_freight_cost)
            + Decimal(self.rto_reverse_freight_cost)
            + Decimal(self.master_carton_and_pick_pack)
            + Decimal(self.transit_breakage_cost)
        )
        self.cm2_amount = _q2(self.cm1_amount - self.total_direct_fulfillment_cost)

        if self.net_revenue > ZERO:
            self.cm1_margin_pct = _q2((self.cm1_amount / self.net_revenue) * Decimal("100.00"))
            self.cm2_margin_pct = _q2((self.cm2_amount / self.net_revenue) * Decimal("100.00"))
        else:
            self.cm1_margin_pct = ZERO
            self.cm2_margin_pct = ZERO

        # Expected payout after marketplace / gateway deductions & returns (before warehouse COGS)
        gross_collectible = _q2(
            Decimal(self.gross_sales_gmv)
            - Decimal(self.discounts_and_rebates)
            - Decimal(self.returns_and_rto_reversal)
        )
        if self.channel in (SalesChannel.AMAZON, SalesChannel.FLIPKART, SalesChannel.SHOPIFY_D2C):
            channel_deductions = _q2(
                Decimal(self.platform_commission_fees)
                + Decimal(self.payment_gateway_fees)
                + Decimal(self.outbound_freight_cost)
                + Decimal(self.rto_reverse_freight_cost)
            )
            self.expected_payout_amount = _q2(gross_collectible - channel_deductions)
        else:
            self.expected_payout_amount = gross_collectible

        if self.reconciliation_status in (ReconciliationStatus.RECONCILED, ReconciliationStatus.DISPUTED):
            self.discrepancy_amount = _q2(self.expected_payout_amount - Decimal(self.actual_settled_payout))

    def save(self, *args, **kwargs):
        self.recalculate_waterfall()
        super().save(*args, **kwargs)


class OrderBatchAllocation(models.Model):
    """
    Granular SKU & FEFO formulation batch attribution for multi-batch COGS splits
    and SKU/Batch profitability exploration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_econ = models.ForeignKey(
        FactOrderUnitEconomics,
        on_delete=models.CASCADE,
        related_name="batch_allocations",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="batch_econ_allocations",
    )
    batch = models.ForeignKey(
        "inventory.Batch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="econ_allocations",
    )
    units_dispatched = models.PositiveIntegerField(default=1)
    unit_batch_cost = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    total_batch_cogs = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    line_net_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    line_packaging_and_inward = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    line_fulfillment_cost = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    line_cm1 = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    line_cm2 = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    class Meta:
        db_table = "fin_order_batch_allocation"
        indexes = [
            models.Index(fields=["product", "batch"]),
        ]

    def save(self, *args, **kwargs):
        self.total_batch_cogs = _q2(Decimal(self.units_dispatched) * Decimal(self.unit_batch_cost))
        self.line_cm1 = _q2(
            Decimal(self.line_net_revenue) - self.total_batch_cogs - Decimal(self.line_packaging_and_inward)
        )
        self.line_cm2 = _q2(self.line_cm1 - Decimal(self.line_fulfillment_cost))
        super().save(*args, **kwargs)


class LossCategory(models.TextChoices):
    FEFO_BATCH_EXPIRY = "FEFO_BATCH_EXPIRY", "Expired Skincare Formulation Batch"
    QC_LAB_REJECTION = "QC_LAB_REJECTION", "QC Rejection / R&D Formulation Wastage"
    TRANSIT_LR_BREAKAGE = "TRANSIT_LR_BREAKAGE", "B2B LR Transit Leakage / Glass Breakage"
    UNRETURNED_RTO_LOSS = "UNRETURNED_RTO_LOSS", "Marketplace Damaged / Lost RTO"
    TESTER_PROMO_BURN = "TESTER_PROMO_BURN", "Complimentary B2B Testers & PR Seeding"
    BAD_DEBT_WRITEOFF = "BAD_DEBT_WRITEOFF", "Defaulted B2B Retailer Receivable"
    MARKETPLACE_SLA_PENALTY = "MARKETPLACE_SLA_PENALTY", "Marketplace SLA / Chargeback Penalty"
    MANUAL_WAREHOUSE_LOSS = "MANUAL_WAREHOUSE_LOSS", "Warehouse Spillage / Theft / Other"


class LossAndLeakageRecord(models.Model):
    """
    Captures both automated ERP losses (FEFO expiry, POD transit breakage)
    and manual loss entries with Maker-Checker approval.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incurred_date = models.DateField(db_index=True)
    category = models.CharField(max_length=32, choices=LossCategory.choices, db_index=True)
    channel = models.CharField(
        max_length=24, choices=SalesChannel.choices, default=SalesChannel.B2B_WHOLESALE
    )
    affected_batch = models.ForeignKey(
        "inventory.Batch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loss_records",
    )
    linked_order_econ = models.ForeignKey(
        FactOrderUnitEconomics,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loss_records",
    )
    units_lost = models.PositiveIntegerField(default=0)
    total_loss_amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    is_manual_entry = models.BooleanField(default=False)
    reason_notes = models.TextField()
    evidence_document = models.FileField(upload_to="finance/loss_evidence/%Y/%m/", null=True, blank=True)

    # Maker-Checker Governance
    approval_status = models.CharField(
        max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="logged_losses",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_losses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fin_loss_and_leakage"
        indexes = [
            models.Index(fields=["incurred_date", "approval_status", "category"]),
        ]


class ExpenseBucket(models.TextChoices):
    # Marketing & Selling Spend (Deducted from CM2 to get CM3)
    META_GOOGLE_ADS = "META_GOOGLE_ADS", "Meta & Google Performance Ads (CM3)"
    MARKETPLACE_ADS = "MARKETPLACE_ADS", "Amazon & Flipkart Sponsored Ads (CM3)"
    SALES_COMMISSIONS = "SALES_COMMISSIONS", "B2B Sales Team Commissions & Incentives (CM3)"
    INFLUENCER_PR = "INFLUENCER_PR", "Influencer Retainers & PR Campaigns (CM3)"
    # Fixed OPEX (Deducted from CM3 to get EBITDA)
    PAYROLL_SALARIES = "PAYROLL_SALARIES", "Company Payroll & Salaries (OPEX)"
    WAREHOUSE_OFFICE_RENT = "WAREHOUSE_OFFICE_RENT", "Warehouse & Office Rent (OPEX)"
    SAAS_CLOUD_INFRA = "SAAS_CLOUD_INFRA", "Cloud, ERP & Software Subscriptions (OPEX)"
    LEGAL_ADMIN_UTILITIES = "LEGAL_ADMIN_UTILITIES", "Legal, CA, Lab Testing & Utilities (OPEX)"


CM3_MARKETING_BUCKETS = {
    ExpenseBucket.META_GOOGLE_ADS,
    ExpenseBucket.MARKETPLACE_ADS,
    ExpenseBucket.SALES_COMMISSIONS,
    ExpenseBucket.INFLUENCER_PR,
}


class MarketingAndOpexEntry(models.Model):
    """
    Stores daily/monthly Marketing Spend (for CM3) and Fixed OPEX (for EBITDA/Net Profit),
    supporting both manual entry and bulk CSV uploads with Maker-Checker approval.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period_start_date = models.DateField(db_index=True)
    period_end_date = models.DateField(db_index=True)
    bucket = models.CharField(max_length=32, choices=ExpenseBucket.choices, db_index=True)
    target_channel = models.CharField(
        max_length=24,
        choices=SalesChannel.choices,
        null=True,
        blank=True,
        help_text="Null means shared company-wide expense prorated across channels",
    )
    amount_exclusive_gst = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    gst_input_credit = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    vendor_or_platform_name = models.CharField(max_length=128)
    is_paid = models.BooleanField(default=True)
    invoice_attachment = models.FileField(upload_to="finance/opex_invoices/%Y/%m/", null=True, blank=True)
    approval_status = models.CharField(
        max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="logged_opex",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_opex",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fin_marketing_and_opex_entry"
        indexes = [
            models.Index(fields=["period_start_date", "period_end_date", "approval_status"]),
        ]

    @property
    def is_cm3_marketing_cost(self) -> bool:
        return self.bucket in CM3_MARKETING_BUCKETS


class ManualRevenueEntry(models.Model):
    """
    Allows manual logging of offline store sales, pop-up exhibitions, or off-system B2B orders.
    Upon Admin approval, optionally deducts FEFO batch stock and posts FactOrderUnitEconomics.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale_date = models.DateField(db_index=True)
    reference_number = models.CharField(max_length=64, unique=True)
    customer_or_store_name = models.CharField(max_length=128)
    sku = models.ForeignKey(
        "inventory.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manual_revenue_entries",
    )
    quantity = models.PositiveIntegerField(default=0)
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    manual_cogs_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    manual_freight_and_packing = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    receipt_attachment = models.FileField(upload_to="finance/manual_sales/%Y/%m/", null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    approval_status = models.CharField(
        max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    posted_economics_row = models.OneToOneField(
        FactOrderUnitEconomics,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manual_source",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="manual_sales_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="manual_sales_approved",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fin_manual_revenue_entry"

    @transaction.atomic
    def approve_and_post_to_ledger(self, admin_user=None) -> FactOrderUnitEconomics:
        """
        Atomically locks the manual entry, deducts FEFO batch stock if linked to SKU & qty > 0,
        computes batch COGS, posts FactOrderUnitEconomics, and writes an immutable AuditLog.
        """
        from inventory.services import InventoryEngine
        from inventory.models import Batch

        locked_self = ManualRevenueEntry.objects.select_for_update().select_related("sku").get(pk=self.pk)
        if locked_self.approval_status == ApprovalStatus.APPROVED and locked_self.posted_economics_row:
            return locked_self.posted_economics_row

        computed_cogs = Decimal(locked_self.manual_cogs_amount)
        batch_allocs = []

        if locked_self.sku and locked_self.quantity > 0:
            outtake_res = InventoryEngine.outtake(
                sku=locked_self.sku.sku,
                quantity=locked_self.quantity,
                source="MANUAL",
                user=admin_user,
            )
            computed_cogs = Decimal("0.00")
            for pick in outtake_res["pick_directions"]:
                qty_picked = int(pick["quantity_picked"])
                unit_cost = locked_self.sku.base_cost
                computed_cogs += Decimal(qty_picked) * unit_cost
                batch_obj = Batch.objects.filter(batch_id=pick["batch_id"]).first()
                batch_allocs.append((locked_self.sku, batch_obj, qty_picked, unit_cost))
            computed_cogs = _q2(computed_cogs)

        econ_row, _ = FactOrderUnitEconomics.objects.update_or_create(
            channel=SalesChannel.MANUAL_OFFLINE,
            external_order_ref=locked_self.reference_number,
            defaults={
                "order_date": locked_self.sale_date,
                "reconciliation_status": ReconciliationStatus.RECONCILED,
                "primary_sku": locked_self.sku,
                "gross_sales_gmv": locked_self.gross_amount,
                "gst_tax_amount": locked_self.gst_amount,
                "discounts_and_rebates": locked_self.discount_amount,
                "batch_formulation_cogs": computed_cogs,
                "outbound_freight_cost": locked_self.manual_freight_and_packing,
                "actual_settled_payout": _q2(
                    Decimal(locked_self.gross_amount) - Decimal(locked_self.discount_amount)
                ),
                "amount_collected": _q2(
                    Decimal(locked_self.gross_amount) - Decimal(locked_self.discount_amount)
                ),
                "settled_at": timezone.now(),
            },
        )

        if batch_allocs:
            econ_row.batch_allocations.all().delete()
            total_units = sum(q for _, _, q, _ in batch_allocs) or 1
            for prod, batch_obj, qty_picked, unit_cost in batch_allocs:
                share = Decimal(qty_picked) / Decimal(total_units)
                OrderBatchAllocation.objects.create(
                    order_econ=econ_row,
                    product=prod,
                    batch=batch_obj,
                    units_dispatched=qty_picked,
                    unit_batch_cost=unit_cost,
                    line_net_revenue=_q2(econ_row.net_revenue * share),
                    line_fulfillment_cost=_q2(econ_row.total_direct_fulfillment_cost * share),
                )

        locked_self.manual_cogs_amount = computed_cogs
        locked_self.approval_status = ApprovalStatus.APPROVED
        locked_self.approved_by = admin_user
        locked_self.posted_economics_row = econ_row
        locked_self.save(
            update_fields=[
                "manual_cogs_amount",
                "approval_status",
                "approved_by",
                "posted_economics_row",
            ]
        )

        FinancialAuditLog.record(
            actor=admin_user,
            action="APPROVE",
            entity_type="ManualRevenueEntry",
            entity_id=str(locked_self.id),
            snapshot={
                "reference_number": locked_self.reference_number,
                "gross_amount": str(locked_self.gross_amount),
                "net_revenue": str(econ_row.net_revenue),
                "batch_formulation_cogs": str(econ_row.batch_formulation_cogs),
                "cm2_amount": str(econ_row.cm2_amount),
            },
            notes=f"Approved manual offline sale {locked_self.reference_number}",
        )
        return econ_row


class FinancialAuditLog(models.Model):
    """Immutable audit log capturing every Maker-Checker approval, rejection, and reconciliation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=32)  # APPROVE, REJECT, RECONCILE, DISPUTE, CREATE
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    snapshot_json = models.JSONField(default=dict)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "fin_audit_log"
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if self._state.adding is False and FinancialAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("FinancialAuditLog is immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FinancialAuditLog is immutable and cannot be deleted.")

    @classmethod
    def record(cls, actor, action: str, entity_type: str, entity_id: str, snapshot: dict, notes: str = ""):
        return cls.objects.create(
            actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            snapshot_json=snapshot,
            notes=notes,
        )


class FinancialTreasuryConfig(models.Model):
    """Stores current Bank Cash Balance, Monthly Interest, and Corporate Tax Rate for Runway."""
    id = models.PositiveIntegerField(primary_key=True, default=1)
    cash_in_bank_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("2500000.00"))
    monthly_interest_expense = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("12500.00"))
    effective_tax_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("25.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fin_treasury_config"

