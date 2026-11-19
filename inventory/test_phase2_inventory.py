from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from inventory.models import (
    Product, Batch, Location, InventoryLedger, TransactionLog,
    SkincareCategory, SkincareLine
)
from inventory.services import InventoryEngine
from inventory.exceptions import InsufficientStockError
from core.models import UserRole, AuditLog, AuditAction

User = get_user_model()


class Phase2MineralSkincareInventoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.today = date.today()

        # Admin user for RBAC authenticated tests
        self.admin_user = User.objects.create_user(
            username='inventory_master', password='Password123!',
            role=UserRole.ADMIN_PROPRIETOR, is_staff=True, is_superuser=True
        )
        self.client.force_authenticate(user=self.admin_user)

        # 1. Flagship Mineral Cleanser / Roll-On
        self.product_cleanser = Product.objects.create(
            sku='PURA-CLEANSE-200',
            name='Purastone Gentle Mineral Gel Cleanser 200ml',
            category=SkincareCategory.MINERAL_CLEANSER,
            skincare_line=SkincareLine.PURA_ALUM_WELLNESS,
            mineral_actives='Natural Potassium Alum, Zinc PCA, Green Tea Extract',
            packaging_format='200ml Recyclable Airless Bottle',
            net_volume_ml_g=Decimal('200.00'),
            barcode_ean13_upc='8901234567801',
            hsn_code='33049990',
            dead_weight_kg=Decimal('0.260'),
            length_cm=Decimal('6.00'),
            width_cm=Decimal('6.00'),
            height_cm=Decimal('18.00'),
            inner_pack_count=6,
            master_carton_qty=24,
            base_price=Decimal('899.00'),
            base_cost=Decimal('220.00'),
            default_b2b_price=Decimal('540.00')
        )

        # 2. Mineral Sunscreen SPF 50
        self.product_sunscreen = Product.objects.create(
            sku='PURA-SOLAR-50',
            name='Purastone Zinc Solar Mineral Shield SPF 50 50g',
            category=SkincareCategory.SUNSCREEN,
            skincare_line=SkincareLine.SOLAR_SHIELD,
            mineral_actives='25% Micronized Non-Nano Zinc Oxide',
            packaging_format='50g Airless Matte Pump Tube',
            net_volume_ml_g=Decimal('50.00'),
            barcode_ean13_upc='8901234567802',
            hsn_code='33049990',
            dead_weight_kg=Decimal('0.090'),
            length_cm=Decimal('4.00'),
            width_cm=Decimal('4.00'),
            height_cm=Decimal('12.00'),
            inner_pack_count=12,
            master_carton_qty=48,
            base_price=Decimal('999.00'),
            base_cost=Decimal('260.00'),
            default_b2b_price=Decimal('620.00')
        )

        # Warehouse locations
        self.loc_main = Location.objects.create(
            warehouse='MUMBAI_CENTRAL', aisle='A1', row='R2', shelf='S01', bin='B01'
        )
        self.loc_secondary = Location.objects.create(
            warehouse='MUMBAI_CENTRAL', aisle='A1', row='R2', shelf='S02', bin='B02'
        )
        self.loc_quarantine = Location.objects.create(
            warehouse='MUMBAI_CENTRAL', aisle='Q9', row='R9', shelf='S99', bin='QUAR'
        )

    def test_01_product_and_sku_directory_attributes_and_filters(self):
        """Verifies skincare classification, mineral actives, barcode, and volumetric weight."""
        # Test calculated weights
        # Volumetric = (6 * 6 * 18) / 5000 = 648 / 5000 = 0.1296 -> 0.130 kg
        self.assertEqual(self.product_cleanser.volumetric_weight_kg, Decimal('0.130'))
        # Chargeable weight = max(dead_weight 0.260, volumetric 0.130) = 0.260
        self.assertEqual(self.product_cleanser.chargeable_weight_kg, Decimal('0.260'))

        # API Filter by Category
        res_cat = self.client.get('/api/products/?category=SUNSCREEN')
        self.assertEqual(res_cat.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cat.data), 1)
        self.assertEqual(res_cat.data[0]['sku'], 'PURA-SOLAR-50')
        self.assertEqual(res_cat.data[0]['category_display'], 'Sunscreens')
        self.assertEqual(res_cat.data[0]['skincare_line_display'], 'Solar Mineral Shield')

        # API Filter by Mineral Active
        res_active = self.client.get('/api/products/?mineral_active=Potassium Alum')
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_active.data), 1)
        self.assertEqual(res_active.data[0]['sku'], 'PURA-CLEANSE-200')

    def test_02_formulation_batch_shelf_life_and_traceability(self):
        """Verifies batch lot tracking, MFD, EXP, near-expiry alert and genealogy report."""
        # 1. Create a fresh batch (Expiring in 300 days)
        batch_fresh = Batch.objects.create(
            batch_id='BATCH-CLN-2026-01',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=65),
            expiry_date=self.today + timedelta(days=300),
            compliance_certificate_number='COA-PURA-2026-991',
            shelf_life_threshold_days=90
        )
        # 2. Create a near-expiry batch (Expiring in 45 days <= 90 threshold)
        batch_near = Batch.objects.create(
            batch_id='BATCH-CLN-2026-NEAR',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=320),
            expiry_date=self.today + timedelta(days=45),
            compliance_certificate_number='COA-PURA-2026-992',
            shelf_life_threshold_days=90
        )

        self.assertFalse(batch_fresh.is_near_expiry)
        self.assertFalse(batch_fresh.is_expired)
        self.assertTrue(batch_fresh.is_sellable_fefo)

        self.assertTrue(batch_near.is_near_expiry)
        self.assertFalse(batch_near.is_expired)
        self.assertTrue(batch_near.is_sellable_fefo)

        # Intake stock across locations
        InventoryEngine.intake(
            sku=self.product_cleanser.sku,
            quantity=50,
            batch_id=batch_fresh.batch_id,
            mfg_date=batch_fresh.mfg_date,
            expiry_date=batch_fresh.expiry_date,
            warehouse=self.loc_main.warehouse,
            aisle=self.loc_main.aisle, row=self.loc_main.row, shelf=self.loc_main.shelf, bin=self.loc_main.bin
        )

        # Query batch traceability endpoint
        res_trace = self.client.get(f'/api/batches/{batch_fresh.batch_id}/')
        self.assertEqual(res_trace.status_code, status.HTTP_200_OK)
        self.assertEqual(res_trace.data['total_inventory_units'], 50)
        self.assertEqual(res_trace.data['compliance_certificate_number'], 'COA-PURA-2026-991')
        self.assertEqual(len(res_trace.data['locations']), 1)

    def test_03_quarantine_batch_exclusion_from_fefo(self):
        """Quarantining a formulation lot must immediately exclude it from sellable FEFO stock."""
        batch = Batch.objects.create(
            batch_id='BATCH-SOLAR-001',
            product=self.product_sunscreen,
            mfg_date=self.today - timedelta(days=10),
            expiry_date=self.today + timedelta(days=365)
        )
        InventoryEngine.intake(
            sku=self.product_sunscreen.sku,
            quantity=100,
            batch_id=batch.batch_id,
            mfg_date=batch.mfg_date,
            expiry_date=batch.expiry_date,
            warehouse=self.loc_main.warehouse,
            aisle=self.loc_main.aisle, row=self.loc_main.row, shelf=self.loc_main.shelf, bin=self.loc_main.bin
        )

        # Available before quarantine = 100
        preview_before = InventoryEngine.simulate_fefo_pick(sku=self.product_sunscreen.sku, quantity=50)
        self.assertTrue(preview_before['is_fulfillable'])

        # Quarantine batch via API
        res_quar = self.client.post(f'/api/batches/{batch.batch_id}/quarantine/', {
            'quarantine': True,
            'reason': 'Microbial test discrepancy in zinc oxide dispersion lot'
        })
        self.assertEqual(res_quar.status_code, status.HTTP_200_OK)
        self.assertTrue(res_quar.data['quarantine_status'])
        self.assertFalse(res_quar.data['is_sellable_fefo'])

        # Verify FEFO outtake now rejects because stock is quarantined
        with self.assertRaises(InsufficientStockError):
            InventoryEngine.outtake(sku=self.product_sunscreen.sku, quantity=10)

        # Release from quarantine
        res_rel = self.client.post(f'/api/batches/{batch.batch_id}/quarantine/', {
            'quarantine': False,
            'reason': 'Secondary third-party lab COA passed all microbial specs'
        })
        self.assertEqual(res_rel.status_code, status.HTTP_200_OK)
        self.assertFalse(res_rel.data['quarantine_status'])

        # Now FEFO outtake succeeds
        outtake = InventoryEngine.outtake(sku=self.product_sunscreen.sku, quantity=10)
        self.assertEqual(outtake['status'], 'SUCCESS')

    def test_04_real_time_fefo_stock_depletion_multi_lot_ordering(self):
        """FEFO must allocate the earliest expiring sellable lot first and skip expired/quarantined lots."""
        # 1. Expired Lot (30 days ago) - Must be skipped
        batch_exp = Batch.objects.create(
            batch_id='BATCH-CLEANSE-EXP',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=400),
            expiry_date=self.today - timedelta(days=30)
        )
        # 2. Lot A (Expiring in 20 days) - Should be depleted FIRST
        batch_a = Batch.objects.create(
            batch_id='BATCH-CLEANSE-LOT-A',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=100),
            expiry_date=self.today + timedelta(days=20)
        )
        # 3. Lot B (Expiring in 120 days) - Should be depleted SECOND
        batch_b = Batch.objects.create(
            batch_id='BATCH-CLEANSE-LOT-B',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=20),
            expiry_date=self.today + timedelta(days=120)
        )
        # 4. Lot C (Expiring in 10 days, but QUARANTINED) - Must be skipped
        batch_quar = Batch.objects.create(
            batch_id='BATCH-CLEANSE-QUAR',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=150),
            expiry_date=self.today + timedelta(days=10),
            quarantine_status=True
        )

        # Stock intake
        InventoryEngine.intake(
            sku=self.product_cleanser.sku, quantity=25, batch_id=batch_exp.batch_id,
            mfg_date=batch_exp.mfg_date, expiry_date=batch_exp.expiry_date,
            warehouse=self.loc_quarantine.warehouse, aisle=self.loc_quarantine.aisle,
            row=self.loc_quarantine.row, shelf=self.loc_quarantine.shelf, bin=self.loc_quarantine.bin
        )
        InventoryEngine.intake(
            sku=self.product_cleanser.sku, quantity=30, batch_id=batch_a.batch_id,
            mfg_date=batch_a.mfg_date, expiry_date=batch_a.expiry_date,
            warehouse=self.loc_main.warehouse, aisle=self.loc_main.aisle,
            row=self.loc_main.row, shelf=self.loc_main.shelf, bin=self.loc_main.bin
        )
        InventoryEngine.intake(
            sku=self.product_cleanser.sku, quantity=40, batch_id=batch_b.batch_id,
            mfg_date=batch_b.mfg_date, expiry_date=batch_b.expiry_date,
            warehouse=self.loc_secondary.warehouse, aisle=self.loc_secondary.aisle,
            row=self.loc_secondary.row, shelf=self.loc_secondary.shelf, bin=self.loc_secondary.bin
        )
        InventoryEngine.intake(
            sku=self.product_cleanser.sku, quantity=15, batch_id=batch_quar.batch_id,
            mfg_date=batch_quar.mfg_date, expiry_date=batch_quar.expiry_date,
            warehouse=self.loc_quarantine.warehouse, aisle=self.loc_quarantine.aisle,
            row=self.loc_quarantine.row, shelf=self.loc_quarantine.shelf, bin=self.loc_quarantine.bin
        )

        # Total sellable stock = 30 (Lot A) + 40 (Lot B) = 70 units
        # Request 45 units: Expect 30 units from Lot A (depleted) and 15 units from Lot B
        outtake = InventoryEngine.outtake(sku=self.product_cleanser.sku, quantity=45)
        self.assertEqual(outtake['status'], 'SUCCESS')
        picks = outtake['pick_directions']
        self.assertEqual(len(picks), 2)

        # First pick: BATCH-CLEANSE-LOT-A, quantity 30
        self.assertEqual(picks[0]['batch_id'], 'BATCH-CLEANSE-LOT-A')
        self.assertEqual(picks[0]['quantity_picked'], 30)

        # Second pick: BATCH-CLEANSE-LOT-B, quantity 15
        self.assertEqual(picks[1]['batch_id'], 'BATCH-CLEANSE-LOT-B')
        self.assertEqual(picks[1]['quantity_picked'], 15)

        # Ledger check: Lot A balance = 0, Lot B balance = 25
        ledger_a = InventoryLedger.objects.get(batch=batch_a, location=self.loc_main)
        ledger_b = InventoryLedger.objects.get(batch=batch_b, location=self.loc_secondary)
        self.assertEqual(ledger_a.quantity, 0)
        self.assertEqual(ledger_b.quantity, 25)

    def test_05_fefo_simulation_preview_api(self):
        """Simulation endpoint previews routing without deducting stock."""
        batch = Batch.objects.create(
            batch_id='BATCH-SOLAR-SIM',
            product=self.product_sunscreen,
            mfg_date=self.today - timedelta(days=15),
            expiry_date=self.today + timedelta(days=60) # near expiry
        )
        InventoryEngine.intake(
            sku=self.product_sunscreen.sku, quantity=100, batch_id=batch.batch_id,
            mfg_date=batch.mfg_date, expiry_date=batch.expiry_date,
            warehouse=self.loc_main.warehouse, aisle=self.loc_main.aisle,
            row=self.loc_main.row, shelf=self.loc_main.shelf, bin=self.loc_main.bin
        )

        res = self.client.post('/api/inventory/fefo-preview/', {
            'sku': self.product_sunscreen.sku,
            'quantity': 40
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertTrue(data['is_fulfillable'])
        self.assertEqual(data['requested_quantity'], 40)
        self.assertTrue(data['contains_near_expiry_batches'])

        # Confirm stock was NOT mutated
        ledger = InventoryLedger.objects.get(batch=batch, location=self.loc_main)
        self.assertEqual(ledger.quantity, 100)

    def test_06_dispatch_gate_pass_fefo_outtake_and_manifest(self):
        """Gate pass dispatch atomically deducts stock, calculates master cartons, and emits audit event."""
        batch = Batch.objects.create(
            batch_id='BATCH-CLN-GP-01',
            product=self.product_cleanser,
            mfg_date=self.today - timedelta(days=30),
            expiry_date=self.today + timedelta(days=180),
            compliance_certificate_number='COA-2026-MUMBAI-01'
        )
        InventoryEngine.intake(
            sku=self.product_cleanser.sku, quantity=48, batch_id=batch.batch_id,
            mfg_date=batch.mfg_date, expiry_date=batch.expiry_date,
            warehouse=self.loc_main.warehouse, aisle=self.loc_main.aisle,
            row=self.loc_main.row, shelf=self.loc_main.shelf, bin=self.loc_main.bin
        )

        res = self.client.post('/api/inventory/dispatch-gate-pass/', {
            'dispatch_reference': 'DISP-AURA-2026-001',
            'gate_pass_number': 'GP-2026-8812',
            'lr_number': 'LR-VRL-9921',
            'items': [
                {'sku': self.product_cleanser.sku, 'quantity': 48}
            ]
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        manifest = res.data
        self.assertEqual(manifest['gate_pass_number'], 'GP-2026-8812')
        self.assertEqual(manifest['lr_number'], 'LR-VRL-9921')
        self.assertEqual(manifest['total_units'], 48)

        # 48 units / 24 master_carton_qty = 2.0 cartons
        self.assertEqual(manifest['total_cartons'], 2.0)
        # 48 * 0.260 kg = 12.480 kg
        self.assertEqual(manifest['total_chargeable_weight_kg'], 12.480)

        # Verify TransactionLog has source='GATE_PASS'
        tlog = TransactionLog.objects.filter(source='GATE_PASS', product=self.product_cleanser).first()
        self.assertIsNotNone(tlog)
        self.assertEqual(tlog.quantity_change, -48)

        # Verify AuditLog has GATE_PASS_ISSUED
        alog = AuditLog.objects.filter(action=AuditAction.GATE_PASS_ISSUED, entity_id='GP-2026-8812').first()
        self.assertIsNotNone(alog)
