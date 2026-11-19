from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from core.models import UserRole, AuditLog, AuditAction
from core.permissions import (
    IsAdminOrProprietor, IsSalesTeam, IsWarehouseSupervisor,
    IsAccountingStaff, IsPrimaryClientRetailer, IsServiceProvider,
    HasRolePermission, RoleBasedAccessPermission
)
from core.services import setup_rbac_groups, AuditService
from core.middleware import AuditContextMiddleware, get_current_audit_context
from inventory.models import Product, Batch, Location, WholesalerParent, WholesalerChild, WholesaleOrder, Invoice
from finance.models import LorryReceipt

User = get_user_model()


class Phase1CoreRBACTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.factory = RequestFactory()

        # Create distinct users for all 6 roles
        self.admin_user = User.objects.create_user(
            username='admin_owner', password='Password123!',
            role=UserRole.ADMIN_PROPRIETOR, is_staff=True, is_superuser=True
        )
        self.sales_user = User.objects.create_user(
            username='sales_rep', password='Password123!',
            role=UserRole.SALES_TEAM
        )
        self.warehouse_user = User.objects.create_user(
            username='wh_supervisor', password='Password123!',
            role=UserRole.WAREHOUSE_DISPATCH_SUPERVISOR
        )
        self.accountant_user = User.objects.create_user(
            username='cfo_accountant', password='Password123!',
            role=UserRole.ACCOUNTING_STAFF
        )
        self.retailer_user = User.objects.create_user(
            username='retail_partner', password='Password123!',
            role=UserRole.PRIMARY_CLIENT_RETAILER, gstin='27AABCU9603R1ZM'
        )
        self.provider_user = User.objects.create_user(
            username='derm_specialist', password='Password123!',
            role=UserRole.SERVICE_PROVIDER
        )

        # Base product and batch for signal tests
        self.product = Product.objects.create(
            sku='PURA-MINERAL-MIST-100',
            name='Purastone Mineral Mist 100ml',
            base_price=Decimal('699.00'),
            base_cost=Decimal('150.00'),
            default_b2b_price=Decimal('420.00')
        )
        self.batch = Batch.objects.create(
            batch_id='BATCH-MIST-001',
            product=self.product,
            mfg_date=date.today() - timedelta(days=30),
            expiry_date=date.today() + timedelta(days=365)
        )
        self.location = Location.objects.create(
            warehouse='MAIN_WH', aisle='A1', row='R1', shelf='S01', bin='B1'
        )

    def test_01_custom_user_roles_and_helpers(self):
        """Validates all 6 discrete roles, property helpers and display labels."""
        self.assertTrue(self.admin_user.is_admin_or_proprietor)
        self.assertTrue(self.admin_user.is_sales_team)
        self.assertTrue(self.admin_user.is_warehouse_supervisor)
        self.assertTrue(self.admin_user.is_accounting_staff)

        self.assertTrue(self.sales_user.is_sales_team)
        self.assertFalse(self.sales_user.is_admin_or_proprietor)
        self.assertFalse(self.sales_user.is_warehouse_supervisor)

        self.assertTrue(self.warehouse_user.is_warehouse_supervisor)
        self.assertFalse(self.warehouse_user.is_accounting_staff)

        self.assertTrue(self.accountant_user.is_accounting_staff)
        self.assertTrue(self.retailer_user.is_primary_client_retailer)
        self.assertTrue(self.provider_user.is_service_provider)

        self.assertEqual(self.retailer_user.gstin, '27AABCU9603R1ZM')
        self.assertEqual(self.admin_user.get_role_display(), 'Admin/Proprietor')

    def test_02_drf_permission_classes_enforcement(self):
        """Verifies RBAC permission classes grant authorized roles and reject others."""
        request = self.factory.get('/api/test/')

        # IsAdminOrProprietor
        perm = IsAdminOrProprietor()
        request.user = self.admin_user
        self.assertTrue(perm.has_permission(request, None))
        request.user = self.sales_user
        self.assertFalse(perm.has_permission(request, None))

        # IsSalesTeam
        perm_sales = IsSalesTeam()
        request.user = self.sales_user
        self.assertTrue(perm_sales.has_permission(request, None))
        request.user = self.warehouse_user
        self.assertFalse(perm_sales.has_permission(request, None))

        # IsWarehouseSupervisor
        perm_wh = IsWarehouseSupervisor()
        request.user = self.warehouse_user
        self.assertTrue(perm_wh.has_permission(request, None))
        request.user = self.accountant_user
        self.assertFalse(perm_wh.has_permission(request, None))

        # IsAccountingStaff
        perm_acc = IsAccountingStaff()
        request.user = self.accountant_user
        self.assertTrue(perm_acc.has_permission(request, None))
        request.user = self.retailer_user
        self.assertFalse(perm_acc.has_permission(request, None))

        # Parameterized HasRolePermission
        perm_combo = HasRolePermission.with_roles(UserRole.SALES_TEAM, UserRole.ACCOUNTING_STAFF)()
        request.user = self.sales_user
        self.assertTrue(perm_combo.has_permission(request, None))
        request.user = self.accountant_user
        self.assertTrue(perm_combo.has_permission(request, None))
        request.user = self.provider_user
        self.assertFalse(perm_combo.has_permission(request, None))

    def test_03_rbac_groups_and_permission_assignment(self):
        """Verifies setup_rbac_groups initializes all 6 groups and assigns model permissions."""
        groups = setup_rbac_groups()
        self.assertEqual(len(groups), 6)
        self.assertIn(UserRole.ADMIN_PROPRIETOR, groups)
        self.assertIn(UserRole.SALES_TEAM, groups)

        admin_group = groups[UserRole.ADMIN_PROPRIETOR]
        sales_group = groups[UserRole.SALES_TEAM]

        self.assertGreater(admin_group.permissions.count(), 0)
        self.assertGreater(sales_group.permissions.count(), 0)

    def test_04_immutable_audit_log_append_only(self):
        """Verifies AuditLog records can be created, but updating or deleting raises PermissionDenied."""
        log = AuditLog.record_action(
            action=AuditAction.PRICE_MODIFICATION,
            entity_type='Product',
            entity_id=self.product.sku,
            actor=self.admin_user,
            pre_snapshot={'default_b2b_price': '420.00'},
            post_snapshot={'default_b2b_price': '450.00'},
            ip_address='192.168.1.10',
            user_agent='Purastone-ERP-Agent/1.0'
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.actor_username, 'admin_owner')
        self.assertEqual(log.delta['default_b2b_price']['before'], '420.00')

        # Attempt to modify: Must raise PermissionDenied
        log.actor_username = 'hacked_username'
        with self.assertRaises(PermissionDenied):
            log.save()

        # Attempt to delete: Must raise PermissionDenied
        with self.assertRaises(PermissionDenied):
            log.delete()

    def test_05_audit_middleware_context_capture(self):
        """Verifies AuditContextMiddleware captures IP, user, and agent into thread context."""
        middleware = AuditContextMiddleware(lambda req: None)
        request = self.factory.get('/api/test/', HTTP_USER_AGENT='TestAgent/2.0', HTTP_X_FORWARDED_FOR='203.0.113.195, 10.0.0.1')
        request.user = self.admin_user

        middleware.process_request(request)
        ctx = get_current_audit_context()
        self.assertEqual(ctx.get('ip_address'), '203.0.113.195')
        self.assertEqual(ctx.get('user_agent'), 'TestAgent/2.0')
        self.assertEqual(ctx.get('user'), self.admin_user)

    def test_06_automated_audit_signal_price_modification(self):
        """Updating Product prices must trigger an automated PRICE_MODIFICATION audit log."""
        initial_log_count = AuditLog.objects.filter(action=AuditAction.PRICE_MODIFICATION, entity_id=str(self.product.sku)).count()

        self.product.default_b2b_price = Decimal('460.00')
        self.product.save()

        logs = AuditLog.objects.filter(action=AuditAction.PRICE_MODIFICATION, entity_id=str(self.product.sku))
        self.assertEqual(logs.count(), initial_log_count + 1)
        latest = logs.first()
        self.assertEqual(latest.pre_change_snapshot['default_b2b_price'], '420.00')
        self.assertEqual(latest.post_change_snapshot['default_b2b_price'], '460.00')

    def test_07_automated_audit_signal_batch_expiry_override(self):
        """Modifying Batch expiry date must trigger an automated BATCH_EXPIRY_OVERRIDE audit log."""
        new_expiry = date.today() + timedelta(days=500)
        self.batch.expiry_date = new_expiry
        self.batch.save()

        logs = AuditLog.objects.filter(action=AuditAction.BATCH_EXPIRY_OVERRIDE, entity_id=str(self.batch.batch_id))
        self.assertGreaterEqual(logs.count(), 1)
        latest = logs.first()
        self.assertEqual(latest.post_change_snapshot['expiry_date'], new_expiry.isoformat())

    def test_08_automated_audit_signal_credit_limit_and_discount(self):
        """Modifying WholesalerParent credit limit and WholesaleOrder discount generates audit logs."""
        parent = WholesalerParent.objects.create(
            name='Luxe Organic Retail',
            gstin='29AAACL1234F1Z8',
            master_email='info@luxeorganic.com',
            status='APPROVED'
        )
        parent.name = 'Luxe Organic Retail Pvt Ltd'
        parent.status = 'APPROVED'
        parent.save()

        child_user = User.objects.create_user(username='luxe_store_1', password='Password123!', role=UserRole.PRIMARY_CLIENT_RETAILER)
        child = WholesalerChild.objects.create(
            parent=parent,
            user=child_user,
            branch_name='Luxe Indiranagar',
            store_id='LUXE-IND-01',
            shipping_address='100 Feet Rd, Bangalore',
            contact_person='Sunil Rao'
        )

        order = WholesaleOrder.objects.create(
            parent_wholesaler=parent,
            child_wholesaler=child,
            status='DRAFT'
        )

        # Apply discount approval
        order.discount_amount = Decimal('500.00')
        order.status = 'DISCOUNT_APPLIED'
        order.save()

        logs = AuditLog.objects.filter(action=AuditAction.DISCOUNT_APPROVAL, entity_id=str(order.id))
        self.assertGreaterEqual(logs.count(), 1)
        latest = logs.first()
        self.assertEqual(latest.post_change_snapshot['discount_amount'], '500.00')
        self.assertEqual(latest.post_change_snapshot['status'], 'DISCOUNT_APPLIED')

    def test_09_health_and_readiness_endpoints(self):
        """Liveness /healthz and readiness /readyz must return HTTP 200 with structured JSON."""
        # Liveness
        res_health = self.client.get('/healthz')
        self.assertEqual(res_health.status_code, status.HTTP_200_OK)
        self.assertEqual(res_health.data['status'], 'healthy')
        self.assertIn('uptime_check', res_health.data)

        # Readiness
        res_ready = self.client.get('/readyz')
        self.assertEqual(res_ready.status_code, status.HTTP_200_OK)
        self.assertIn(res_ready.data['status'], ('ready', 'not_ready'))
        self.assertIn('database', res_ready.data['checks'])

    def test_10_auth_and_audit_api_endpoints(self):
        """Login and Audit-log explorer endpoints return valid tokens, profiles, and permission gates."""
        # 1. Login API
        res_login = self.client.post('/api/core/auth/login/', {
            'username': 'admin_owner',
            'password': 'Password123!'
        })
        self.assertEqual(res_login.status_code, status.HTTP_200_OK)
        self.assertEqual(res_login.data['roles']['primary'], UserRole.ADMIN_PROPRIETOR)
        self.assertTrue(res_login.data['roles']['is_admin'])

        # 2. Me API
        self.client.force_authenticate(user=self.admin_user)
        res_me = self.client.get('/api/core/auth/me/')
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)
        self.assertEqual(res_me.data['user']['username'], 'admin_owner')

        # 3. Audit Explorer API: Admin has access
        res_audit = self.client.get('/api/core/audit-logs/')
        self.assertEqual(res_audit.status_code, status.HTTP_200_OK)

        # 4. Audit Explorer API: Retailer user is denied (403 Forbidden)
        self.client.force_authenticate(user=self.retailer_user)
        res_audit_denied = self.client.get('/api/core/audit-logs/')
        self.assertEqual(res_audit_denied.status_code, status.HTTP_403_FORBIDDEN)
