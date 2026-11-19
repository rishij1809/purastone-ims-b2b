import math
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from inventory.models import (
    Product, Batch, Location, InventoryLedger,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem,
    WholesalerTier, DiscountMode, PricingTierSlab, PromotionalCampaign
)
from inventory.services import WholesalePricingEngine, WholesalerService
from inventory.exceptions import NegativeMarginError
from core.models import AuditLog, AuditAction

User = get_user_model()


class Phase3WholesalePricingTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Admin user
        self.admin_user = User.objects.create_superuser(
            username='phase3_admin',
            email='phase3_admin@purastone.com',
            password='Password@123'
        )

        # Products: Main mineral serum and a complimentary tester cleanse SKU
        self.serum = Product.objects.create(
            sku='PURA-SERUM-50ML',
            name='Pura Stone Mineral Glow Facial Serum 50ml',
            category='SERUM',
            skincare_line='MINERAL_GLOW',
            mineral_actives='Zinc Oxide, Silica, Potassium Alum',
            packaging_format='50ml Glass Dropper Bottle',
            net_volume_ml_g=Decimal('50.00'),
            barcode_ean13_upc='8901234567890',
            hsn_code='33049990',
            dead_weight_kg=Decimal('0.150'),
            length_cm=Decimal('4.00'),
            width_cm=Decimal('4.00'),
            height_cm=Decimal('12.00'),
            inner_pack_count=6,
            master_carton_qty=24,
            base_price=Decimal('1200.00'), # MRP
            base_cost=Decimal('300.00'),   # Formulation COGS
            default_b2b_price=Decimal('900.00') # Base PTR (25% off MRP)
        )

        self.tester_cleanser = Product.objects.create(
            sku='PURA-CLEANSE-SAMPLE',
            name='Pura Mineral Cleanser 15ml Sample',
            category='MINERAL_CLEANSER',
            skincare_line='PURA_ALUM_WELLNESS',
            mineral_actives='Potassium Alum, Kaolin Clay',
            packaging_format='15ml Mini Squeeze Tube',
            net_volume_ml_g=Decimal('15.00'),
            barcode_ean13_upc='8901234567899',
            hsn_code='33049990',
            dead_weight_kg=Decimal('0.030'),
            length_cm=Decimal('2.00'),
            width_cm=Decimal('2.00'),
            height_cm=Decimal('8.00'),
            inner_pack_count=1,
            master_carton_qty=50,
            base_price=Decimal('200.00'),
            base_cost=Decimal('40.00'),
            default_b2b_price=Decimal('150.00')
        )

        # Setup standard inventory stock
        self.location = Location.objects.create(
            warehouse='WH-MUMBAI-MAIN',
            aisle='A1',
            row='R1',
            shelf='S1',
            bin='B1'
        )
        self.batch = Batch.objects.create(
            batch_id='BATCH-SERUM-2026-001',
            product=self.serum,
            mfg_date=date.today() - timedelta(days=30),
            expiry_date=date.today() + timedelta(days=700),
            shelf_life_days=730,
            quarantine_status=False
        )
        InventoryLedger.objects.create(
            product=self.serum,
            batch=self.batch,
            location=self.location,
            quantity=5000
        )

        # Valid 15-character GSTIN
        self.valid_gstin = '27AAPFU0939F1ZV'

        # Onboard Retailer Parent
        self.retailer = WholesalerService.onboard_parent(
            name='Glow & Pure Wellness Retail LLP',
            gstin=self.valid_gstin,
            master_email='procurement@glowandpure.com',
            tier=WholesalerTier.RETAILER,
            trade_license_number='TL-MH-MUM-2026-991',
            cosmetic_license_number='MH-FDA-20B-78812',
            billing_address='Suite 401, Linking Road, Bandra West',
            shipping_address='Warehouse 12, Bhiwandi Logistics Park',
            city='Mumbai',
            state='Maharashtra',
            pincode='400050',
            assigned_credit_limit=Decimal('500000.00'),
            credit_period_days=45,
            discount_mode=DiscountMode.PERCENTAGE,
            show_discount_on_invoice=True
        )
        WholesalerService.approve_parent(self.retailer.id)

        # Branch
        self.child = WholesalerService.create_child_account(
            parent_id=self.retailer.id,
            branch_name='Glow & Pure Flagship Bandra',
            store_id='GP-BANDRA-01',
            shipping_address='Linking Road Bandra West, Mumbai 400050',
            contact_person='Sunita Mehta',
            username='glow_bandra',
            password='Password@123'
        )

    def test_01_retailer_profile_and_gstin_validation(self):
        """Verify B2B profile captures licenses, coordinates and validates 15-char GSTIN format."""
        self.assertEqual(self.retailer.tier, WholesalerTier.RETAILER)
        self.assertEqual(self.retailer.trade_license_number, 'TL-MH-MUM-2026-991')
        self.assertEqual(self.retailer.cosmetic_license_number, 'MH-FDA-20B-78812')
        self.assertEqual(self.retailer.assigned_credit_limit, Decimal('500000.00'))
        self.assertEqual(self.retailer.credit_period_days, 45)
        self.assertTrue(self.retailer.show_discount_on_invoice)

        # Test GSTIN validator rejects malformed inputs
        self.assertFalse(WholesalePricingEngine.validate_gstin('INVALID123'))
        self.assertFalse(WholesalePricingEngine.validate_gstin('27AAPFU0939F1')) # too short
        self.assertTrue(WholesalePricingEngine.validate_gstin('27AAPFU0939F1ZV'))

        with self.assertRaises(ValueError):
            WholesalerService.onboard_parent(
                name='Fake Store',
                gstin='NOT-A-VALID-GST',
                master_email='fake@store.com'
            )

    def test_02_credit_limit_modification_triggers_immutable_audit_log(self):
        """Updating credit limit or credit period logs an immutable record in core.AuditLog."""
        initial_log_count = AuditLog.objects.filter(entity_type='WholesalerParent').count()

        # Update credit limit
        self.retailer.assigned_credit_limit = Decimal('750000.00')
        self.retailer.credit_period_days = 60
        self.retailer.save()

        logs = AuditLog.objects.filter(
            entity_type='WholesalerParent',
            action=AuditAction.CREDIT_LIMIT_CHANGE
        ).order_by('-timestamp')

        self.assertGreater(logs.count(), initial_log_count)
        latest = logs.first()
        self.assertEqual(latest.post_snapshot['assigned_credit_limit'], '750000.00')
        self.assertEqual(latest.post_snapshot['credit_period_days'], 60)

    def test_03_volume_slab_calculation_across_cartons(self):
        """Verify tiered volume slabs automatically scale wholesale unit prices and discounts."""
        # 1-5 cartons (24-120 units): 25% PTR discount -> Rs 900
        PricingTierSlab.objects.create(
            product=self.serum,
            tier=WholesalerTier.RETAILER,
            min_cartons=1,
            max_cartons=5,
            ptr_discount_pct=Decimal('25.00'),
            pts_discount_pct=Decimal('35.00')
        )
        # 6-20 cartons (144-480 units): 32% volume discount -> Rs 816
        PricingTierSlab.objects.create(
            product=self.serum,
            tier=WholesalerTier.RETAILER,
            min_cartons=6,
            max_cartons=20,
            ptr_discount_pct=Decimal('32.00'),
            pts_discount_pct=Decimal('40.00')
        )
        # 21+ cartons: 38% super volume discount -> Rs 744
        PricingTierSlab.objects.create(
            product=self.serum,
            tier=WholesalerTier.RETAILER,
            min_cartons=21,
            max_cartons=None,
            ptr_discount_pct=Decimal('38.00'),
            pts_discount_pct=Decimal('45.00')
        )

        # Test small tier (2 cartons = 48 units)
        sim_small = WholesalePricingEngine.simulate_order_profitability(
            items=[{'sku': self.serum.sku, 'quantity': 48}],
            parent=self.retailer
        )
        item_small = sim_small['items'][0]
        self.assertEqual(item_small['cartons'], 2)
        self.assertEqual(Decimal(item_small['applied_discount_pct']), Decimal('25.00'))
        self.assertEqual(Decimal(item_small['unit_price']), Decimal('900.00'))

        # Test mid tier (10 cartons = 240 units)
        sim_mid = WholesalePricingEngine.simulate_order_profitability(
            items=[{'sku': self.serum.sku, 'quantity': 240}],
            parent=self.retailer
        )
        item_mid = sim_mid['items'][0]
        self.assertEqual(item_mid['cartons'], 10)
        self.assertEqual(Decimal(item_mid['applied_discount_pct']), Decimal('32.00'))
        self.assertEqual(Decimal(item_mid['unit_price']), Decimal('816.00'))

        # Test bulk tier (25 cartons = 600 units)
        sim_bulk = WholesalePricingEngine.simulate_order_profitability(
            items=[{'sku': self.serum.sku, 'quantity': 600}],
            parent=self.retailer
        )
        item_bulk = sim_bulk['items'][0]
        self.assertEqual(item_bulk['cartons'], 25)
        self.assertEqual(Decimal(item_bulk['applied_discount_pct']), Decimal('38.00'))
        self.assertEqual(Decimal(item_bulk['unit_price']), Decimal('744.00'))

    def test_04_promotional_campaign_and_complimentary_tester_seeding(self):
        """Festive campaigns apply discounts and allocate complimentary tester units without distorting COGS."""
        campaign = PromotionalCampaign.objects.create(
            campaign_code='DIWALI-2026',
            name='Diwali Mineral Festive Campaign',
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=20),
            discount_pct=Decimal('5.00'), # extra 5% promotional discount
            allocated_budget=Decimal('50000.00'),
            complimentary_tester_sku=self.tester_cleanser,
            tester_quantity_per_order=4 # 4 free mini cleansers
        )

        sim = WholesalePricingEngine.simulate_order_profitability(
            items=[{'sku': self.serum.sku, 'quantity': 48}], # 2 cartons @ 900 = Rs 43,200 subtotal
            parent=self.retailer,
            campaign_code='DIWALI-2026',
            estimated_freight=Decimal('1200.00'),
            packaging_cost=Decimal('300.00')
        )

        self.assertEqual(sim['status'], 'APPROVED_PROFITABLE')
        self.assertEqual(sim['campaign_applied'], 'DIWALI-2026')
        self.assertEqual(Decimal(sim['subtotal']), Decimal('43200.00'))
        # 5% of 43,200 = 2,160.00
        self.assertEqual(Decimal(sim['promotional_discount']), Decimal('2160.00'))
        # Final value = 43,200 - 2,160 = 41,040.00
        self.assertEqual(Decimal(sim['final_value']), Decimal('41040.00'))

        # Tester bundle verification
        tester_info = sim['tester_bundle']
        self.assertIsNotNone(tester_info)
        self.assertEqual(tester_info['sku'], self.tester_cleanser.sku)
        self.assertEqual(tester_info['quantity'], 4)
        self.assertEqual(tester_info['charge_to_customer'], '0.00')
        # 4 testers x Rs 40 COGS = Rs 160.00 tester COGS
        self.assertEqual(Decimal(sim['tester_cogs']), Decimal('160.00'))
        # Product COGS = 48 x 300 = 14,400. Total order COGS = 14,400 + 160 = 14,560.00
        self.assertEqual(Decimal(sim['total_cogs']), Decimal('14560.00'))

    def test_05_strict_price_floor_protection_negative_margin_error(self):
        """Simulation and order creation strictly reject quotations that yield negative margins below formulation COGS."""
        # Formulation COGS for 48 units = 48 x 300 = Rs 14,400
        # If user forces an unprofitable unit price of Rs 250 (below COGS Rs 300):
        with self.assertRaises(NegativeMarginError) as ctx:
            WholesalePricingEngine.simulate_order_profitability(
                items=[{'sku': self.serum.sku, 'quantity': 48, 'unit_price': '250.00'}],
                parent=self.retailer
            )
        self.assertIn("Quotation yields negative margin", str(ctx.exception))
        self.assertIn("below total formulation COGS floor", str(ctx.exception))

        # Also verify that draft order creation via WholesalerService aborts atomically on negative margin
        with self.assertRaises(NegativeMarginError):
            WholesalerService.create_draft_order(
                child_id=self.child.id,
                items=[{'sku': self.serum.sku, 'quantity': 48, 'unit_price': '250.00'}]
            )

    def test_06_pre_dispatch_calculator_api_endpoint(self):
        """API endpoint /api/wholesale/quotation-calculator/ returns profitability simulation and enforces floor."""
        payload = {
            "parent_id": self.retailer.id,
            "estimated_freight": "850.00",
            "packaging_cost": "250.00",
            "items": [
                {"sku": self.serum.sku, "quantity": 48}
            ]
        }
        res = self.client.post('/api/wholesale/quotation-calculator/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], 'APPROVED_PROFITABLE')
        self.assertEqual(Decimal(data['subtotal']), Decimal('43200.00'))
        self.assertEqual(Decimal(data['variable_overheads']), Decimal('1100.00'))
        self.assertGreater(Decimal(data['net_margin_yield_pct']), Decimal('0.00'))

        # Test rejected negative margin via API
        bad_payload = {
            "parent_id": self.retailer.id,
            "estimated_freight": "10000.00",
            "packaging_cost": "5000.00",
            "items": [
                {"sku": self.serum.sku, "quantity": 48, "unit_price": "290.00"} # below 300 COGS
            ]
        }
        bad_res = self.client.post('/api/wholesale/quotation-calculator/', bad_payload, format='json')
        self.assertEqual(bad_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bad_res.json()['status'], 'REJECTED_NEGATIVE_MARGIN')
        self.assertIn('below total formulation COGS floor', bad_res.json()['error'])

    def test_07_pricing_tier_slab_crud_apis(self):
        """API endpoints for CRUD on dynamic pricing tier slabs."""
        # Create slab
        create_payload = {
            "tier": "STOCKIST",
            "min_cartons": 5,
            "max_cartons": 20,
            "ptr_discount_pct": "28.00",
            "pts_discount_pct": "38.50"
        }
        res = self.client.post('/api/wholesale/pricing-slabs/', create_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        slab_id = res.json()['id']

        # List slabs
        list_res = self.client.get('/api/wholesale/pricing-slabs/?tier=STOCKIST')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(s['id'] == slab_id for s in list_res.json()))

        # Update slab
        patch_res = self.client.patch(f'/api/wholesale/pricing-slabs/{slab_id}/', {'pts_discount_pct': '40.00'}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(patch_res.json()['pts_discount_pct']), Decimal('40.00'))

    def test_08_order_creation_persists_simulation_metrics_and_tester_bundle(self):
        """Order creation persists net margins, freight estimates and tester bundles."""
        campaign = PromotionalCampaign.objects.create(
            campaign_code='PR-LAUNCH-2026',
            name='Pura Mineral PR Launch Seeding',
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=30),
            discount_pct=Decimal('2.50'),
            allocated_budget=Decimal('20000.00'),
            complimentary_tester_sku=self.tester_cleanser,
            tester_quantity_per_order=2
        )

        order = WholesalerService.create_draft_order(
            child_id=self.child.id,
            items=[{'sku': self.serum.sku, 'quantity': 48}],
            campaign_code='PR-LAUNCH-2026',
            estimated_freight=Decimal('800.00'),
            packaging_cost=Decimal('200.00'),
            notes='Test order with PR campaign'
        )

        self.assertIsNotNone(order.campaign)
        self.assertEqual(order.campaign.campaign_code, 'PR-LAUNCH-2026')
        self.assertEqual(order.estimated_freight, Decimal('800.00'))
        self.assertEqual(order.packaging_cost, Decimal('200.00'))
        self.assertGreater(order.gross_margin, Decimal('0.00'))
        self.assertGreater(order.net_margin_yield_pct, Decimal('0.00'))
        self.assertEqual(order.tester_bundle_info['sku'], self.tester_cleanser.sku)
        self.assertEqual(order.tester_bundle_info['quantity'], 2)

        # Check line item
        line = order.items.first()
        self.assertEqual(line.mrp_unit, Decimal('1200.00'))
        self.assertEqual(line.locked_base_cost, Decimal('300.00'))
        self.assertEqual(line.locked_b2b_price, Decimal('900.00'))
