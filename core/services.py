from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core.models import UserRole, AuditLog, AuditAction
from core.middleware import get_current_audit_context


def setup_rbac_groups() -> dict:
    """
    Configures standard Django auth groups and maps appropriate model permissions
    for each of the 6 discrete roles in Pura Stone ERP.
    """
    created_groups = {}

    group_definitions = {
        UserRole.ADMIN_PROPRIETOR: {
            "name": "Admin / Proprietor",
            "permissions": "__all__"  # Full system access
        },
        UserRole.SALES_TEAM: {
            "name": "Sales Team",
            "permissions": [
                "view_product", "view_batch",
                "add_wholesalerparent", "change_wholesalerparent", "view_wholesalerparent",
                "add_wholesalerchild", "change_wholesalerchild", "view_wholesalerchild",
                "add_wholesaleorder", "change_wholesaleorder", "view_wholesaleorder",
                "view_invoice", "view_lorryreceipt",
            ]
        },
        UserRole.WAREHOUSE_DISPATCH_SUPERVISOR: {
            "name": "Warehouse / Dispatch Supervisor",
            "permissions": [
                "view_product", "add_batch", "change_batch", "view_batch",
                "add_inventoryledger", "view_inventoryledger",
                "view_transactionlog",
                "view_wholesaleorder", "change_wholesaleorder",
                "add_lorryreceipt", "change_lorryreceipt", "view_lorryreceipt",
                "add_batchexpirywriteoff", "view_batchexpirywriteoff",
            ]
        },
        UserRole.ACCOUNTING_STAFF: {
            "name": "Accounting Staff",
            "permissions": [
                "view_product", "view_wholesaleorder",
                "add_invoice", "change_invoice", "view_invoice",
                "view_lorryreceipt",
                "add_marketingandopexentry", "change_marketingandopexentry", "view_marketingandopexentry",
                "add_manualrevenueentry", "change_manualrevenueentry", "view_manualrevenueentry",
                "add_lossandleakagerecord", "change_lossandleakagerecord", "view_lossandleakagerecord",
                "view_factorderuniteconomics",
            ]
        },
        UserRole.PRIMARY_CLIENT_RETAILER: {
            "name": "Primary Client / Retailer",
            "permissions": [
                "view_product",
                "add_wholesaleorder", "view_wholesaleorder",
                "view_invoice", "view_lorryreceipt",
            ]
        },
        UserRole.SERVICE_PROVIDER: {
            "name": "Service Provider",
            "permissions": [
                "view_product",
            ]
        }
    }

    all_permissions = list(Permission.objects.all())

    for role_code, defn in group_definitions.items():
        group, _ = Group.objects.get_or_create(name=defn["name"])
        created_groups[role_code] = group

        if defn["permissions"] == "__all__":
            group.permissions.set(all_permissions)
        else:
            perms_to_add = []
            for codename in defn["permissions"]:
                matching = [p for p in all_permissions if p.codename == codename]
                if matching:
                    perms_to_add.extend(matching)
            group.permissions.set(perms_to_add)

    return created_groups


class AuditService:
    """
    Centralized service for logging immutable audit records across all modules.
    Automatically enriches entries with HTTP context (IP, user-agent, actor) from middleware.
    """

    @classmethod
    def log(
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
        user_agent: str = None,
    ) -> AuditLog:
        ctx = get_current_audit_context()

        resolved_actor = actor or ctx.get('user')
        resolved_ip = ip_address or ctx.get('ip_address')
        resolved_ua = user_agent or ctx.get('user_agent')

        merged_metadata = dict(metadata or {})
        if ctx.get('path'):
            merged_metadata.setdefault('path', ctx.get('path'))
        if ctx.get('method'):
            merged_metadata.setdefault('method', ctx.get('method'))

        return AuditLog.record_action(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            actor=resolved_actor,
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            delta=delta,
            metadata=merged_metadata,
            ip_address=resolved_ip,
            user_agent=resolved_ua,
        )
