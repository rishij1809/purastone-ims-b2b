from rest_framework import serializers
from .models import (
    ChannelSkuMapping,
    LorryReceipt,
    BatchExpiryWriteOff,
    FactOrderUnitEconomics,
    OrderBatchAllocation,
    LossAndLeakageRecord,
    MarketingAndOpexEntry,
    ManualRevenueEntry,
    FinancialAuditLog,
    FinancialTreasuryConfig,
)


class ChannelSkuMappingSerializer(serializers.ModelSerializer):
    internal_sku_name = serializers.CharField(source="internal_sku.name", read_only=True)

    class Meta:
        model = ChannelSkuMapping
        fields = [
            "id", "internal_sku", "internal_sku_name", "channel",
            "external_product_id", "external_sku_code",
            "default_platform_commission_pct", "default_packaging_cost_per_unit",
            "default_inward_freight_per_unit", "is_active",
        ]


class LorryReceiptSerializer(serializers.ModelSerializer):
    order_po = serializers.CharField(source="wholesale_order.po_number", read_only=True)

    class Meta:
        model = LorryReceipt
        fields = [
            "id", "lr_number", "wholesale_order", "order_po", "transporter_name",
            "freight_mode", "freight_amount", "ancillary_packaging_cost",
            "transporter_payable_status", "payable_due_date", "pod_status",
            "pod_damage_units", "pod_damage_cost", "pod_notes", "pod_verified_at", "created_at",
        ]


class BatchExpiryWriteOffSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="batch.product.sku", read_only=True)

    class Meta:
        model = BatchExpiryWriteOff
        fields = [
            "id", "batch", "sku", "writeoff_date", "units_written_off",
            "unit_cost", "total_writeoff_value", "notes", "created_at",
        ]
        read_only_fields = ["total_writeoff_value"]


class OrderBatchAllocationSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    batch_code = serializers.CharField(source="batch.batch_id", read_only=True)

    class Meta:
        model = OrderBatchAllocation
        fields = [
            "id", "sku", "batch_code", "units_dispatched", "unit_batch_cost",
            "total_batch_cogs", "line_net_revenue", "line_packaging_and_inward",
            "line_fulfillment_cost", "line_cm1", "line_cm2",
        ]


class FactOrderUnitEconomicsSerializer(serializers.ModelSerializer):
    batch_allocations = OrderBatchAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = FactOrderUnitEconomics
        fields = "__all__"


class LossAndLeakageRecordSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    batch_code = serializers.CharField(source="affected_batch.batch_id", read_only=True)

    class Meta:
        model = LossAndLeakageRecord
        fields = [
            "id", "incurred_date", "category", "category_label", "channel",
            "affected_batch", "batch_code", "units_lost", "total_loss_amount",
            "is_manual_entry", "reason_notes", "evidence_document",
            "approval_status", "created_at",
        ]
        read_only_fields = ["is_manual_entry", "approval_status", "created_at"]


class MarketingAndOpexEntrySerializer(serializers.ModelSerializer):
    bucket_label = serializers.CharField(source="get_bucket_display", read_only=True)
    is_cm3 = serializers.BooleanField(source="is_cm3_marketing_cost", read_only=True)

    class Meta:
        model = MarketingAndOpexEntry
        fields = [
            "id", "period_start_date", "period_end_date", "bucket", "bucket_label",
            "is_cm3", "target_channel", "amount_exclusive_gst", "gst_input_credit",
            "vendor_or_platform_name", "is_paid", "invoice_attachment",
            "approval_status", "created_at",
        ]
        read_only_fields = ["approval_status", "created_at"]


class ManualRevenueEntrySerializer(serializers.ModelSerializer):
    sku_name = serializers.CharField(source="sku.name", read_only=True)

    class Meta:
        model = ManualRevenueEntry
        fields = [
            "id", "sale_date", "reference_number", "customer_or_store_name",
            "sku", "sku_name", "quantity", "gross_amount", "gst_amount",
            "discount_amount", "manual_cogs_amount", "manual_freight_and_packing",
            "receipt_attachment", "notes", "approval_status", "posted_economics_row", "created_at",
        ]
        read_only_fields = ["approval_status", "posted_economics_row", "created_at"]


class FinancialAuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = FinancialAuditLog
        fields = ["id", "timestamp", "actor_username", "action", "entity_type", "entity_id", "snapshot_json", "notes"]


class FinancialTreasuryConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialTreasuryConfig
        fields = ["cash_in_bank_balance", "monthly_interest_expense", "effective_tax_rate_pct", "updated_at"]

