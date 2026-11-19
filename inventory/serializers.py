from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from .models import (
    Product, BundleMapping, Batch, Location, InventoryLedger, TransactionLog,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem, Invoice,
    WholesalerTier, DiscountMode, PricingTierSlab, PromotionalCampaign
)
from .services import WholesalePricingEngine


class ProductSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    skincare_line_display = serializers.CharField(source='get_skincare_line_display', read_only=True)
    volumetric_weight_kg = serializers.DecimalField(max_digits=8, decimal_places=3, read_only=True)
    chargeable_weight_kg = serializers.DecimalField(max_digits=8, decimal_places=3, read_only=True)
    total_sellable_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'sku', 'name', 'category', 'category_display',
            'skincare_line', 'skincare_line_display',
            'mineral_actives', 'packaging_format', 'net_volume_ml_g',
            'barcode_ean13_upc', 'hsn_code',
            'dead_weight_kg', 'length_cm', 'width_cm', 'height_cm',
            'volumetric_weight_kg', 'chargeable_weight_kg',
            'inner_pack_count', 'master_carton_qty',
            'base_price', 'base_cost', 'default_b2b_price',
            'total_sellable_stock'
        ]

    def get_total_sellable_stock(self, obj) -> int:
        from django.utils import timezone
        today = timezone.now().date()
        total = InventoryLedger.objects.filter(
            product=obj,
            quantity__gt=0,
            batch__expiry_date__gte=today,
            batch__quarantine_status=False
        ).aggregate(total=Sum('quantity'))['total']
        return total or 0


class BundleMappingSerializer(serializers.ModelSerializer):
    base_product_sku = serializers.CharField(source='base_product.sku', read_only=True)

    class Meta:
        model = BundleMapping
        fields = ['promo_sku', 'base_product', 'base_product_sku', 'quantity_multiplier']


class IntakeSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)
    batch_id = serializers.CharField(max_length=100)
    mfg_date = serializers.DateField()
    expiry_date = serializers.DateField()
    warehouse = serializers.CharField(max_length=50)
    aisle = serializers.CharField(max_length=20)
    row = serializers.CharField(max_length=20)
    shelf = serializers.CharField(max_length=20)
    bin = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    source = serializers.CharField(max_length=20, default='MANUAL')


class OuttakeSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)
    source = serializers.CharField(max_length=20, default='MANUAL')


class ManualAdjustmentSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    batch_id = serializers.CharField(max_length=100)
    location_id = serializers.UUIDField()
    quantity_change = serializers.IntegerField()
    reason_code = serializers.CharField(max_length=255, required=True, allow_blank=False)


class OrderItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)


class OrderPayloadSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=100)
    source = serializers.ChoiceField(choices=['AMAZON', 'SHOPIFY', 'FLIPKART', 'MANUAL', 'WHOLESALE'])
    items = OrderItemSerializer(many=True)


class TransactionLogSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    batch_id = serializers.CharField(source='batch.batch_id', read_only=True, allow_null=True)
    username = serializers.CharField(source='user.username', read_only=True, allow_null=True)

    class Meta:
        model = TransactionLog
        fields = [
            'id', 'timestamp', 'product_sku', 'batch_id', 'location',
            'quantity_change', 'transaction_type', 'source', 'reason_code', 'username'
        ]


# ==========================================
# WHOLESALER MODULE SERIALIZERS
# ==========================================

class WholesalerChildSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model = WholesalerChild
        fields = [
            'id', 'parent', 'parent_name', 'username', 'branch_name',
            'store_id', 'shipping_address', 'contact_person'
        ]


class WholesalerParentSerializer(serializers.ModelSerializer):
    branches = WholesalerChildSerializer(many=True, read_only=True)
    branches_count = serializers.IntegerField(source='branches.count', read_only=True)

    class Meta:
        model = WholesalerParent
        fields = ['id', 'name', 'gstin', 'master_email', 'status', 'created_at', 'branches_count', 'branches']


class WholesalerChildCreateSerializer(serializers.Serializer):
    parent_id = serializers.IntegerField()
    branch_name = serializers.CharField(max_length=255)
    store_id = serializers.CharField(max_length=100)
    shipping_address = serializers.CharField()
    contact_person = serializers.CharField(max_length=255)
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, required=False, allow_blank=True)


class WholesaleOrderItemSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source='product.sku', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = WholesaleOrderItem
        fields = [
            'id', 'sku', 'product_name', 'quantity', 'locked_base_cost',
            'locked_b2b_price', 'gst_percentage', 'gst_amount', 'line_total'
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'pdf_url', 'created_at']


class WholesaleOrderSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent_wholesaler.name', read_only=True)
    branch_name = serializers.CharField(source='child_wholesaler.branch_name', read_only=True)
    store_id = serializers.CharField(source='child_wholesaler.store_id', read_only=True)
    items = WholesaleOrderItemSerializer(many=True, read_only=True)
    invoice = InvoiceSerializer(read_only=True)

    class Meta:
        model = WholesaleOrder
        fields = [
            'id', 'parent_wholesaler', 'parent_name', 'child_wholesaler',
            'branch_name', 'store_id', 'status', 'po_number', 'notes',
            'subtotal', 'discount_amount', 'final_value', 'total_gst', 'grand_total',
            'total_cogs', 'net_profit', 'created_at', 'updated_at',
            'items', 'invoice'
        ]


class WholesaleOrderCreateItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=0)
    gst_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=18.0)


class WholesaleOrderCreateSerializer(serializers.Serializer):
    child_id = serializers.IntegerField()
    po_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = WholesaleOrderCreateItemSerializer(many=True)


class WholesaleDiscountSerializer(serializers.Serializer):
    discount_type = serializers.ChoiceField(choices=['FLAT', 'PERCENTAGE'])
    discount_value = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


# ==========================================
# PHASE 2: BATCH TRACEABILITY & FEFO DISPATCH
# ==========================================

class BatchSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)
    is_near_expiry = serializers.BooleanField(read_only=True)
    is_sellable_fefo = serializers.BooleanField(read_only=True)
    total_quantity = serializers.SerializerMethodField()
    locations = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = [
            'batch_id', 'product', 'product_sku', 'product_name',
            'mfg_date', 'expiry_date', 'shelf_life_days',
            'shelf_life_threshold_days', 'quarantine_status',
            'compliance_certificate_number', 'coa_document',
            'formulation_notes', 'is_expired', 'days_to_expiry',
            'is_near_expiry', 'is_sellable_fefo', 'total_quantity',
            'locations'
        ]

    def get_total_quantity(self, obj) -> int:
        total = InventoryLedger.objects.filter(batch=obj).aggregate(total=Sum('quantity'))['total']
        return total or 0

    def get_locations(self, obj) -> list:
        ledgers = InventoryLedger.objects.filter(batch=obj, quantity__gt=0).select_related('location')
        return [
            {
                "location_id": str(l.location.id),
                "warehouse": l.location.warehouse,
                "shelf_code": f"{l.location.warehouse}:{l.location.aisle}-{l.location.row}-{l.location.shelf}",
                "bin": l.location.bin,
                "quantity": l.quantity
            }
            for l in ledgers
        ]


class BatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Batch
        fields = [
            'batch_id', 'product', 'mfg_date', 'expiry_date',
            'shelf_life_days', 'shelf_life_threshold_days',
            'compliance_certificate_number', 'coa_document',
            'formulation_notes'
        ]

    def validate(self, attrs):
        mfg = attrs.get('mfg_date')
        exp = attrs.get('expiry_date')
        if mfg and exp and exp <= mfg:
            raise serializers.ValidationError("Expiry date must be strictly after the manufacturing date.")
        return attrs


class BatchQuarantineSerializer(serializers.Serializer):
    quarantine = serializers.BooleanField(required=True)
    reason = serializers.CharField(required=True, min_length=5)


class FefoSimulationSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)


class DispatchGatePassItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)


class DispatchGatePassSerializer(serializers.Serializer):
    dispatch_reference = serializers.CharField(max_length=100)
    gate_pass_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    lr_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    items = DispatchGatePassItemSerializer(many=True)


# ==========================================
# PHASE 3 WHOLESALE & PRICING SERIALIZERS
# ==========================================

class WholesalerProfileSerializer(serializers.ModelSerializer):
    tier_display = serializers.CharField(source='get_tier_display', read_only=True)
    discount_mode_display = serializers.CharField(source='get_discount_mode_display', read_only=True)
    total_orders_count = serializers.SerializerMethodField()

    class Meta:
        model = WholesalerParent
        fields = [
            'id', 'name', 'tier', 'tier_display',
            'trade_license_number', 'cosmetic_license_number',
            'gstin', 'master_email',
            'billing_address', 'shipping_address', 'city', 'state', 'pincode',
            'assigned_credit_limit', 'credit_period_days',
            'discount_mode', 'discount_mode_display', 'show_discount_on_invoice',
            'status', 'created_at', 'total_orders_count'
        ]

    def get_total_orders_count(self, obj) -> int:
        return WholesaleOrder.objects.filter(parent_wholesaler=obj).count()

    def validate_gstin(self, value):
        val = value.strip().upper()
        if not WholesalePricingEngine.validate_gstin(val):
            raise serializers.ValidationError(
                f"Invalid Indian GSTIN '{val}'. Must be exactly 15 characters conforming to statutory GSTIN regex format."
            )
        return val


class PricingTierSlabSerializer(serializers.ModelSerializer):
    tier_display = serializers.CharField(source='get_tier_display', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True, allow_null=True)
    product_name = serializers.CharField(source='product.name', read_only=True, allow_null=True)

    class Meta:
        model = PricingTierSlab
        fields = [
            'id', 'product', 'product_sku', 'product_name',
            'tier', 'tier_display',
            'min_cartons', 'max_cartons',
            'ptr_discount_pct', 'pts_discount_pct', 'custom_unit_price',
            'is_active', 'created_at', 'updated_at'
        ]

    def validate(self, attrs):
        min_c = attrs.get('min_cartons') or getattr(self.instance, 'min_cartons', 1)
        max_c = attrs.get('max_cartons') if 'max_cartons' in attrs else getattr(self.instance, 'max_cartons', None)
        if max_c is not None and max_c < min_c:
            raise serializers.ValidationError("max_cartons must be greater than or equal to min_cartons.")
        return attrs


class PromotionalCampaignSerializer(serializers.ModelSerializer):
    is_currently_valid = serializers.BooleanField(read_only=True)
    complimentary_tester_sku_code = serializers.CharField(source='complimentary_tester_sku.sku', read_only=True, allow_null=True)
    complimentary_tester_sku_name = serializers.CharField(source='complimentary_tester_sku.name', read_only=True, allow_null=True)

    class Meta:
        model = PromotionalCampaign
        fields = [
            'id', 'campaign_code', 'name', 'description',
            'start_date', 'end_date',
            'discount_pct', 'flat_discount_amount',
            'is_active', 'is_currently_valid',
            'allocated_budget', 'consumed_discount_total',
            'applicable_skus',
            'complimentary_tester_sku', 'complimentary_tester_sku_code', 'complimentary_tester_sku_name',
            'tester_quantity_per_order',
            'created_at', 'updated_at'
        ]

    def validate(self, attrs):
        start = attrs.get('start_date') or getattr(self.instance, 'start_date', None)
        end = attrs.get('end_date') or getattr(self.instance, 'end_date', None)
        if start and end and end < start:
            raise serializers.ValidationError("end_date must be on or after start_date.")
        return attrs


class ProfitabilitySimulationItemInputSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    gst_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)


class ProfitabilitySimulationRequestSerializer(serializers.Serializer):
    parent_id = serializers.IntegerField(required=False, allow_null=True)
    campaign_code = serializers.CharField(max_length=50, required=False, allow_null=True, allow_blank=True)
    estimated_freight = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)
    packaging_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)
    items = ProfitabilitySimulationItemInputSerializer(many=True)

