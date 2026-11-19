from decimal import Decimal
from datetime import date
from django.db import models
from django.conf import settings
import uuid

# ==========================================
# 1. CORE INVENTORY & PRODUCT MODELS
# ==========================================

class SkincareCategory(models.TextChoices):
    MINERAL_CLEANSER = 'MINERAL_CLEANSER', 'Mineral Cleansers'
    CLAY_MASK = 'CLAY_MASK', 'Clay Masks'
    SERUM = 'SERUM', 'Serums'
    MOISTURIZER = 'MOISTURIZER', 'Moisturizers'
    EXFOLIANT = 'EXFOLIANT', 'Exfoliants'
    SUNSCREEN = 'SUNSCREEN', 'Sunscreens'
    OTHER = 'OTHER', 'Other Skincare'


class SkincareLine(models.TextChoices):
    PURA_ALUM_WELLNESS = 'PURA_ALUM_WELLNESS', 'Pura Alum Natural Wellness'
    MINERAL_GLOW = 'MINERAL_GLOW', 'Mineral Glow Skincare'
    DERMA_PURIFYING = 'DERMA_PURIFYING', 'Derma Purifying Care'
    SOLAR_SHIELD = 'SOLAR_SHIELD', 'Solar Mineral Shield'
    CORE_MINERALS = 'CORE_MINERALS', 'Core Mineral Formulas'


class Product(models.Model):
    sku = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(
        max_length=50,
        choices=SkincareCategory.choices,
        default=SkincareCategory.OTHER,
        db_index=True,
        help_text="Primary mineral skincare category"
    )
    skincare_line = models.CharField(
        max_length=50,
        choices=SkincareLine.choices,
        default=SkincareLine.CORE_MINERALS,
        db_index=True,
        help_text="Target formulation collection"
    )
    mineral_actives = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Key mineral actives, e.g. Potassium Alum, Kaolin Clay, Zinc Oxide"
    )
    packaging_format = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Packaging specification, e.g. 50ml Glass Dropper, 100ml Airless Pump Bottle"
    )
    net_volume_ml_g = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('100.00'),
        help_text="Net volume or weight per SKU in ml or g"
    )
    barcode_ean13_upc = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
        help_text="Universal EAN-13 or UPC barcode"
    )
    hsn_code = models.CharField(
        max_length=20,
        default='33049990',
        help_text="Harmonized System Nomenclature code for cosmetics (default 33049990)"
    )
    dead_weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('0.250'),
        help_text="Unit dead weight for logistics in kg"
    )
    length_cm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    width_cm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('15.00'))
    inner_pack_count = models.PositiveIntegerField(default=1, help_text="Units per inner box")
    master_carton_qty = models.PositiveIntegerField(default=24, help_text="Units per master shipping carton")

    base_price = models.DecimalField(max_digits=10, decimal_places=2) # B2C Marketplace price / MRP
    base_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00')) # COGS
    default_b2b_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00')) # B2B Base (PTR)

    def __str__(self):
        return f"{self.sku} - {self.name} (B2C: {self.base_price}, B2B: {self.default_b2b_price}, COGS: {self.base_cost})"

    @property
    def volumetric_weight_kg(self) -> Decimal:
        """Standard air freight volumetric factor: (L x W x H) / 5000"""
        volume_cm3 = self.length_cm * self.width_cm * self.height_cm
        return (volume_cm3 / Decimal('5000.00')).quantize(Decimal('0.001'))

    @property
    def chargeable_weight_kg(self) -> Decimal:
        return max(self.dead_weight_kg, self.volumetric_weight_kg)


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
    shelf_life_days = models.PositiveIntegerField(default=730, help_text="Total formulated shelf life in days")
    shelf_life_threshold_days = models.PositiveIntegerField(
        default=90,
        help_text="Days prior to expiry triggering near-expiry quarantine warnings"
    )
    quarantine_status = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if quarantined or failed compliance inspection"
    )
    coa_document = models.FileField(
        upload_to='coa_documents/',
        null=True,
        blank=True,
        help_text="Certificate of Analysis (COA) document"
    )
    compliance_certificate_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Batch testing lab certification ID"
    )
    formulation_notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['expiry_date', 'mfg_date']

    def __str__(self):
        status_tag = " [QUARANTINED]" if self.quarantine_status else (" [EXPIRED]" if self.is_expired else "")
        return f"{self.batch_id} ({self.product.sku}) - Exp: {self.expiry_date}{status_tag}"

    @property
    def is_expired(self) -> bool:
        return self.expiry_date <= date.today()

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry_date - date.today()).days

    @property
    def is_near_expiry(self) -> bool:
        remaining = self.days_to_expiry
        return 0 < remaining <= self.shelf_life_threshold_days

    @property
    def is_sellable_fefo(self) -> bool:
        return not self.quarantine_status and not self.is_expired

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
        ('GATE_PASS', 'Dispatch Gate Pass'),
        ('LR_DISPATCH', 'Lorry Receipt Dispatch'),
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

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
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE) # The actual login ID
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
