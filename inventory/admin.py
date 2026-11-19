from django.contrib import admin
from .models import (
    Product, Batch, Location, InventoryLedger, TransactionLog,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem,
    Invoice, PricingTierSlab, PromotionalCampaign
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category', 'skincare_line', 'base_price', 'default_b2b_price', 'base_cost')
    search_fields = ('sku', 'name', 'barcode_ean13_upc')
    list_filter = ('category', 'skincare_line')


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('batch_id', 'product', 'mfg_date', 'expiry_date', 'quarantine_status')
    search_fields = ('batch_id', 'product__sku')
    list_filter = ('quarantine_status',)


@admin.register(WholesalerParent)
class WholesalerParentAdmin(admin.ModelAdmin):
    list_display = ('name', 'gstin', 'tier', 'status', 'assigned_credit_limit', 'credit_period_days')
    search_fields = ('name', 'gstin', 'master_email')
    list_filter = ('tier', 'status')


@admin.register(WholesalerChild)
class WholesalerChildAdmin(admin.ModelAdmin):
    list_display = ('branch_name', 'store_id', 'parent', 'contact_person')
    search_fields = ('branch_name', 'store_id')


@admin.register(PricingTierSlab)
class PricingTierSlabAdmin(admin.ModelAdmin):
    list_display = ('tier', 'product', 'min_cartons', 'max_cartons', 'ptr_discount_pct', 'pts_discount_pct', 'is_active')
    list_filter = ('tier', 'is_active')


@admin.register(PromotionalCampaign)
class PromotionalCampaignAdmin(admin.ModelAdmin):
    list_display = ('campaign_code', 'name', 'start_date', 'end_date', 'discount_pct', 'is_active')
    search_fields = ('campaign_code', 'name')
    list_filter = ('is_active',)


@admin.register(WholesaleOrder)
class WholesaleOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent_wholesaler', 'status', 'final_value', 'grand_total', 'net_profit', 'created_at')
    list_filter = ('status',)


admin.site.register(Location)
admin.site.register(InventoryLedger)
admin.site.register(TransactionLog)
admin.site.register(WholesaleOrderItem)
admin.site.register(Invoice)

