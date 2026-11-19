from decimal import Decimal
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from core.models import AuditAction
from core.services import AuditService


def _serialize_val(val):
    if isinstance(val, Decimal):
        return str(val)
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return val


# 1. Product Price Modifications
@receiver(pre_save, sender='inventory.Product')
def capture_product_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._pre_snapshot = {
                'base_cost': _serialize_val(prev.base_cost),
                'default_b2b_price': _serialize_val(prev.default_b2b_price),
                'mrp': _serialize_val(getattr(prev, 'base_price', Decimal('0.00'))),
            }
        except sender.DoesNotExist:
            instance._pre_snapshot = None
    else:
        instance._pre_snapshot = None


@receiver(post_save, sender='inventory.Product')
def audit_product_post_save(sender, instance, created, **kwargs):
    if created or not getattr(instance, '_pre_snapshot', None):
        return

    post_snapshot = {
        'base_cost': _serialize_val(instance.base_cost),
        'default_b2b_price': _serialize_val(instance.default_b2b_price),
        'mrp': _serialize_val(getattr(instance, 'base_price', Decimal('0.00'))),
    }

    pre = instance._pre_snapshot
    price_changed = (
        pre['base_cost'] != post_snapshot['base_cost'] or
        pre['default_b2b_price'] != post_snapshot['default_b2b_price'] or
        pre['mrp'] != post_snapshot['mrp']
    )

    if price_changed:
        AuditService.log(
            action=AuditAction.PRICE_MODIFICATION,
            entity_type='Product',
            entity_id=str(instance.pk),
            pre_snapshot=pre,
            post_snapshot=post_snapshot,
            metadata={'sku': instance.sku, 'name': instance.name}
        )


# 2. Batch Expiry Overrides
@receiver(pre_save, sender='inventory.Batch')
def capture_batch_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._pre_snapshot = {
                'expiry_date': _serialize_val(prev.expiry_date),
                'quarantine_status': getattr(prev, 'quarantine_status', False),
            }
        except sender.DoesNotExist:
            instance._pre_snapshot = None
    else:
        instance._pre_snapshot = None


@receiver(post_save, sender='inventory.Batch')
def audit_batch_post_save(sender, instance, created, **kwargs):
    if created or not getattr(instance, '_pre_snapshot', None):
        return

    post_snapshot = {
        'expiry_date': _serialize_val(instance.expiry_date),
        'quarantine_status': getattr(instance, 'quarantine_status', False),
    }

    pre = instance._pre_snapshot
    expiry_changed = (
        pre['expiry_date'] != post_snapshot['expiry_date'] or
        pre['quarantine_status'] != post_snapshot['quarantine_status']
    )

    if expiry_changed:
        AuditService.log(
            action=AuditAction.BATCH_EXPIRY_OVERRIDE,
            entity_type='Batch',
            entity_id=str(instance.pk),
            pre_snapshot=pre,
            post_snapshot=post_snapshot,
            metadata={'batch_id': getattr(instance, 'batch_id', str(instance.pk)), 'product_id': instance.product_id}
        )


# 3. Wholesaler Credit Limit & Period Changes
@receiver(pre_save, sender='inventory.WholesalerParent')
def capture_wholesaler_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._pre_snapshot = {
                'assigned_credit_limit': _serialize_val(getattr(prev, 'assigned_credit_limit', Decimal('0.00'))),
                'credit_period_days': getattr(prev, 'credit_period_days', 30),
                'status': prev.status,
            }
        except sender.DoesNotExist:
            instance._pre_snapshot = None
    else:
        instance._pre_snapshot = None


@receiver(post_save, sender='inventory.WholesalerParent')
def audit_wholesaler_post_save(sender, instance, created, **kwargs):
    if created or not getattr(instance, '_pre_snapshot', None):
        return

    post_snapshot = {
        'assigned_credit_limit': _serialize_val(getattr(instance, 'assigned_credit_limit', Decimal('0.00'))),
        'credit_period_days': getattr(instance, 'credit_period_days', 30),
        'status': instance.status,
    }

    pre = instance._pre_snapshot
    credit_changed = (
        pre['assigned_credit_limit'] != post_snapshot['assigned_credit_limit'] or
        pre['credit_period_days'] != post_snapshot['credit_period_days']
    )

    if credit_changed:
        company_name = getattr(instance, 'company_name', getattr(instance, 'name', ''))
        AuditService.log(
            action=AuditAction.CREDIT_LIMIT_CHANGE,
            entity_type='WholesalerParent',
            entity_id=str(instance.pk),
            pre_snapshot=pre,
            post_snapshot=post_snapshot,
            metadata={'company_name': company_name, 'gstin': instance.gstin}
        )


# 4. Wholesale Order Discount Approvals
@receiver(pre_save, sender='inventory.WholesaleOrder')
def capture_order_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._pre_snapshot = {
                'discount_amount': _serialize_val(getattr(prev, 'discount_amount', Decimal('0.00'))),
                'final_value': _serialize_val(getattr(prev, 'final_value', Decimal('0.00'))),
                'status': prev.status,
            }
        except sender.DoesNotExist:
            instance._pre_snapshot = None
    else:
        instance._pre_snapshot = None


@receiver(post_save, sender='inventory.WholesaleOrder')
def audit_order_post_save(sender, instance, created, **kwargs):
    if created or not getattr(instance, '_pre_snapshot', None):
        return

    post_snapshot = {
        'discount_amount': _serialize_val(getattr(instance, 'discount_amount', Decimal('0.00'))),
        'final_value': _serialize_val(getattr(instance, 'final_value', Decimal('0.00'))),
        'status': instance.status,
    }

    pre = instance._pre_snapshot
    discount_changed = (
        pre['discount_amount'] != post_snapshot['discount_amount'] or
        (pre['status'] != 'DISCOUNT_APPLIED' and post_snapshot['status'] == 'DISCOUNT_APPLIED')
    )

    if discount_changed:
        AuditService.log(
            action=AuditAction.DISCOUNT_APPROVAL,
            entity_type='WholesaleOrder',
            entity_id=str(instance.pk),
            pre_snapshot=pre,
            post_snapshot=post_snapshot,
            metadata={
                'parent_id': instance.parent_wholesaler_id,
                'status': instance.status,
            }
        )


# 5. Invoice Cancellations
@receiver(pre_save, sender='inventory.Invoice')
def capture_invoice_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            prev = sender.objects.get(pk=instance.pk)
            instance._pre_snapshot = {
                'status': getattr(prev, 'status', 'ISSUED'),
            }
        except sender.DoesNotExist:
            instance._pre_snapshot = None
    else:
        instance._pre_snapshot = None


@receiver(post_save, sender='inventory.Invoice')
def audit_invoice_post_save(sender, instance, created, **kwargs):
    if created or not getattr(instance, '_pre_snapshot', None):
        return

    pre = instance._pre_snapshot
    current_status = getattr(instance, 'status', 'ISSUED')

    if pre['status'] != 'CANCELLED' and current_status == 'CANCELLED':
        AuditService.log(
            action=AuditAction.INVOICE_CANCELLATION,
            entity_type='Invoice',
            entity_id=str(instance.pk),
            pre_snapshot=pre,
            post_snapshot={'status': 'CANCELLED'},
            metadata={'invoice_number': getattr(instance, 'invoice_number', str(instance.pk))}
        )


# 6. Lorry Receipt (LR) Reprints
try:
    from finance.models import LorryReceipt

    @receiver(pre_save, sender=LorryReceipt)
    def capture_lr_pre_save(sender, instance, **kwargs):
        if instance.pk:
            try:
                prev = sender.objects.get(pk=instance.pk)
                instance._pre_snapshot = {
                    'reprint_count': getattr(prev, 'reprint_count', 0),
                    'lr_status': getattr(prev, 'lr_status', 'IN_TRANSIT'),
                }
            except sender.DoesNotExist:
                instance._pre_snapshot = None
        else:
            instance._pre_snapshot = None

    @receiver(post_save, sender=LorryReceipt)
    def audit_lr_post_save(sender, instance, created, **kwargs):
        if created or not getattr(instance, '_pre_snapshot', None):
            return

        pre = instance._pre_snapshot
        current_reprints = getattr(instance, 'reprint_count', 0)

        if current_reprints > pre.get('reprint_count', 0):
            AuditService.log(
                action=AuditAction.LR_REPRINT,
                entity_type='LorryReceipt',
                entity_id=str(instance.pk),
                pre_snapshot=pre,
                post_snapshot={'reprint_count': current_reprints, 'lr_status': instance.lr_status},
                metadata={'lr_number': instance.lr_number}
            )
except ImportError:
    pass
