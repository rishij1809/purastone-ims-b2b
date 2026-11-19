import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db import models


class UserRole(models.TextChoices):
    ADMIN_PROPRIETOR = 'ADMIN_PROPRIETOR', 'Admin/Proprietor'
    SALES_TEAM = 'SALES_TEAM', 'Sales Team'
    WAREHOUSE_DISPATCH_SUPERVISOR = 'WAREHOUSE_DISPATCH_SUPERVISOR', 'Warehouse/Dispatch Supervisor'
    ACCOUNTING_STAFF = 'ACCOUNTING_STAFF', 'Accounting Staff'
    PRIMARY_CLIENT_RETAILER = 'PRIMARY_CLIENT_RETAILER', 'Primary Client/Retailer'
    SERVICE_PROVIDER = 'SERVICE_PROVIDER', 'Service Provider'


class User(AbstractUser):
    """
    Custom User Model for Pura Stone Skincare ERP with granular RBAC roles
    and enterprise wholesale/client identity attributes.
    """
    role = models.CharField(
        max_length=50,
        choices=UserRole.choices,
        default=UserRole.ADMIN_PROPRIETOR,
        db_index=True,
        help_text="Primary RBAC role governing ERP permissions and access level."
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    gstin = models.CharField(max_length=15, blank=True, null=True, help_text="15-digit Indian GSTIN format")
    license_number = models.CharField(max_length=100, blank=True, null=True, help_text="Drug & Cosmetic / Trade License")
    company_name = models.CharField(max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False, help_text="KYC / License verification status")
    assigned_credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Pre-approved credit threshold for wholesale procurement"
    )
    credit_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Standard credit settlement window in days"
    )

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        role_label = self.get_role_display() if hasattr(self, 'get_role_display') else self.role
        return f"{self.username} ({role_label})"

    @property
    def is_admin_or_proprietor(self) -> bool:
        return self.is_superuser or self.is_staff or self.role == UserRole.ADMIN_PROPRIETOR

    @property
    def is_sales_team(self) -> bool:
        return self.is_admin_or_proprietor or self.role == UserRole.SALES_TEAM

    @property
    def is_warehouse_supervisor(self) -> bool:
        return self.is_admin_or_proprietor or self.role == UserRole.WAREHOUSE_DISPATCH_SUPERVISOR

    @property
    def is_accounting_staff(self) -> bool:
        return self.is_admin_or_proprietor or self.role == UserRole.ACCOUNTING_STAFF

    @property
    def is_primary_client_retailer(self) -> bool:
        return self.role == UserRole.PRIMARY_CLIENT_RETAILER

    @property
    def is_service_provider(self) -> bool:
        return self.role == UserRole.SERVICE_PROVIDER

    def has_role(self, *roles: str) -> bool:
        if self.is_superuser:
            return True
        return self.role in roles


class AuditAction(models.TextChoices):
    PRICE_MODIFICATION = 'PRICE_MODIFICATION', 'Price Modification'
    BATCH_EXPIRY_OVERRIDE = 'BATCH_EXPIRY_OVERRIDE', 'Batch Expiry Override'
    LR_REPRINT = 'LR_REPRINT', 'Lorry Receipt (LR) Reprint'
    INVOICE_CANCELLATION = 'INVOICE_CANCELLATION', 'Invoice Cancellation'
    CREDIT_LIMIT_CHANGE = 'CREDIT_LIMIT_CHANGE', 'Credit Limit Change'
    DISCOUNT_APPROVAL = 'DISCOUNT_APPROVAL', 'Discount Approval'
    STOCK_OUTTAKE = 'STOCK_OUTTAKE', 'FEFO Stock Outtake'
    STOCK_ADJUSTMENT = 'STOCK_ADJUSTMENT', 'Manual Stock Adjustment'
    GATE_PASS_ISSUED = 'GATE_PASS_ISSUED', 'Dispatch Gate Pass Issued'
    SETTLEMENT_RECONCILED = 'SETTLEMENT_RECONCILED', 'Settlement Reconciled'
    USER_ROLE_CHANGED = 'USER_ROLE_CHANGED', 'User Role Changed'
    GENERIC_UPDATE = 'GENERIC_UPDATE', 'Generic Record Update'
    GENERIC_DELETE = 'GENERIC_DELETE', 'Generic Record Deletion'


class AuditLog(models.Model):
    """
    Immutable, Append-Only System Audit Log.
    Captures actor ID, IP, user-agent, timestamp, entity type, pre-change JSON snapshot,
    post-change JSON snapshot, and computed delta for all sensitive ERP operations.
    Direct modification or deletion of rows is strictly prevented at the model level.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='system_audit_logs',
        db_index=True
    )
    actor_username = models.CharField(max_length=150, blank=True)
    actor_role = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    action = models.CharField(max_length=100, db_index=True)
    entity_type = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    pre_change_snapshot = models.JSONField(null=True, blank=True)
    post_change_snapshot = models.JSONField(null=True, blank=True)
    delta = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['actor', 'timestamp']),
        ]

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.action} on {self.entity_type}#{self.entity_id} by {self.actor_username or 'SYSTEM'}"

    def save(self, *args, **kwargs):
        # Enforce append-only immutability: updates to existing rows are forbidden
        if not self._state.adding and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("AuditLog entries are strictly append-only and immutable. Existing records cannot be modified.")
        if self.actor and not self.actor_username:
            self.actor_username = getattr(self.actor, 'username', '')
            self.actor_role = getattr(self.actor, 'role', '')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Enforce immutability: deletion of audit logs is forbidden
        raise PermissionDenied("AuditLog records are immutable and cannot be deleted from the database.")

    @classmethod
    def record_action(
        cls,
        action: str,
        entity_type: str,
        entity_id: str,
        actor=None,
        pre_snapshot: dict = None,
        post_snapshot: dict = None,
        delta: dict = None,
        metadata: dict = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> 'AuditLog':
        """
        Helper method to record an immutable audit entry cleanly.
        """
        # If delta not explicitly provided, compute from pre and post snapshots
        if delta is None and pre_snapshot is not None and post_snapshot is not None:
            computed_delta = {}
            all_keys = set(pre_snapshot.keys()) | set(post_snapshot.keys())
            for k in all_keys:
                old_val = pre_snapshot.get(k)
                new_val = post_snapshot.get(k)
                if old_val != new_val:
                    computed_delta[k] = {"before": old_val, "after": new_val}
            delta = computed_delta

        return cls.objects.create(
            actor=actor if (actor and getattr(actor, 'is_authenticated', False)) else None,
            actor_username=getattr(actor, 'username', 'SYSTEM') if actor else 'SYSTEM',
            actor_role=getattr(actor, 'role', '') if actor else '',
            ip_address=ip_address,
            user_agent=user_agent or '',
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            pre_change_snapshot=pre_snapshot,
            post_change_snapshot=post_snapshot,
            delta=delta or {},
            metadata=metadata or {}
        )
