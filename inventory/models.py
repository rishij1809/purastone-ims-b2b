from django.db import models
from django.contrib.auth.models import User
import uuid

# ==========================================
# 1. CORE INVENTORY & PRODUCT MODELS
# ==========================================

class Product(models.Model):
    sku = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    base_price = models.DecimalField(max_digits=10, decimal_places=2) # B2C Marketplace price
    base_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # COGS
    default_b2b_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # B2B Base

    def __str__(self):
        return f"{self.sku} (B2C: {self.base_price}, B2B: {self.default_b2b_price}, COGS: {self.base_cost})"

class BundleMapping(models.Model):
    """Handles BOGO and promotional SKUs arriving from marketplaces."""
    promo_sku = models.CharField(max_length=100, unique=True, db_index=True)
    base_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bundles')
    quantity_multiplier = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.promo_sku} -> {self.base_product.sku} (x{self.quantity_multiplier})"

class Batch(models.Model):
    batch_id = models.CharField(max_length=100, primary_key=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    mfg_date = models.DateField()
    expiry_date = models.DateField(db_index=True)

    def __str__(self):
        return f"{self.batch_id} ({self.product.sku}) - Exp: {self.expiry_date}"

class Location(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    warehouse = models.CharField(max_length=50)
    aisle = models.CharField(max_length=20)
    row = models.CharField(max_length=20)
    shelf = models.CharField(max_length=20)
    bin = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['warehouse', 'aisle', 'row', 'shelf', 'bin'], name='unique_location')
        ]

    def __str__(self):
        bin_str = f"-{self.bin}" if self.bin else ""
        return f"{self.warehouse}:{self.aisle}-{self.row}-{self.shelf}{bin_str}"

class InventoryLedger(models.Model):
    """The absolute source of truth for current stock."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'batch', 'location'], name='unique_inventory_record')
        ]

    def __str__(self):
        return f"{self.product.sku} | {self.batch.batch_id} @ {self.location} = {self.quantity}"

class TransactionLog(models.Model):
    """Immutable ledger of every single movement."""
    TRANSACTION_TYPES = [
        ('INTAKE', 'Intake'),
        ('OUTTAKE', 'Outtake'),
        ('ADJUST', 'Manual Adjustment'),
    ]
    SOURCES = [
        ('AMAZON', 'Amazon'),
        ('SHOPIFY', 'Shopify'),
        ('FLIPKART', 'Flipkart'),
        ('MANUAL', 'Manual'),
        ('WHOLESALE', 'Wholesale Order'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True)
    quantity_change = models.IntegerField()
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    source = models.CharField(max_length=20, choices=SOURCES)
    reason_code = models.CharField(max_length=255, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self._state.adding is False and TransactionLog.objects.filter(pk=self.pk).exists():
            raise ValueError("TransactionLog is immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("TransactionLog is immutable and cannot be deleted.")

    def __str__(self):
        return f"{self.timestamp} | {self.transaction_type} {self.quantity_change} {self.product.sku} ({self.source})"

# ==========================================
# 2. WHOLESALER MANAGEMENT MODELS
# ==========================================

class WholesalerParent(models.Model):
    name = models.CharField(max_length=255)
    gstin = models.CharField(max_length=50, unique=True)
    master_email = models.EmailField(unique=True)
    status = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pending Approval'), ('APPROVED', 'Approved')],
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.gstin}) [{self.status}]"

class WholesalerChild(models.Model):
    parent = models.ForeignKey(WholesalerParent, on_delete=models.CASCADE, related_name='branches')
    user = models.OneToOneField(User, on_delete=models.CASCADE) # The actual login ID
    branch_name = models.CharField(max_length=255)
    store_id = models.CharField(max_length=100, unique=True)
    shipping_address = models.TextField()
    contact_person = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.branch_name} ({self.store_id}) -> Parent: {self.parent.name}"

class WholesaleOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_wholesaler = models.ForeignKey(WholesalerParent, on_delete=models.PROTECT, related_name='all_orders')
    child_wholesaler = models.ForeignKey(WholesalerChild, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(
        max_length=30,
        choices=[
            ('DRAFT', 'Draft'),
            ('DISCOUNT_APPLIED', 'Discount Applied'),
            ('CONFIRMED', 'Confirmed'),
            ('FULFILLED', 'Fulfilled')
        ],
        default='DRAFT'
    )
    
    # Financial Ledgers
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    final_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_cogs = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    po_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WholesaleOrder {self.id} | {self.child_wholesaler.branch_name} | {self.status} | Final: ₹{self.final_value}"

class WholesaleOrderItem(models.Model):
    order = models.ForeignKey(WholesaleOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    
    # Immutable cost/price fields to protect historical data
    locked_base_cost = models.DecimalField(max_digits=10, decimal_places=2)
    locked_b2b_price = models.DecimalField(max_digits=10, decimal_places=2)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.product.sku} x {self.quantity} (B2B Price: {self.locked_b2b_price}, Cost: {self.locked_base_cost})"

class Invoice(models.Model):
    order = models.OneToOneField(WholesaleOrder, on_delete=models.CASCADE, related_name='invoice')
    pdf_url = models.URLField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice for Order {self.order.id} ({self.pdf_url})"
