from rest_framework import serializers
from .models import (
    Product, BundleMapping, Batch, Location, InventoryLedger, TransactionLog,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem, Invoice
)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['sku', 'name', 'base_price', 'base_cost', 'default_b2b_price']


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
