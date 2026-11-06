from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Product, Batch, Location, InventoryLedger, TransactionLog, BundleMapping
from .services import InventoryEngine
from .exceptions import InsufficientStockError, InvalidAdjustmentError, ProductNotFoundError
from .integrations import ChannelRateLimiter, ADAPTER_REGISTRY
from .tasks import sync_channel_inventory_task


class CoreInventoryEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='warehouse_op', password='password123')
        self.today = timezone.now().date()
        
        # Base Product
        self.product = Product.objects.create(
            sku="LIPSTICK-RUBY-01",
            name="Ruby Matte Lipstick",
            base_price=Decimal("499.00")
        )
        
        # BOGO Promotional SKU: 1 PROMO-BOGO-LIPSTICK = 2 LIPSTICK-RUBY-01
        self.bundle = BundleMapping.objects.create(
            promo_sku="PROMO-BOGO-LIPSTICK",
            base_product=self.product,
            quantity_multiplier=2
        )

    def test_01_intake_creates_batch_location_ledger_and_transaction(self):
        result = InventoryEngine.intake(
            sku=self.product.sku,
            quantity=50,
            batch_id="BATCH-2026-A",
            mfg_date=self.today - timedelta(days=10),
            expiry_date=self.today + timedelta(days=365),
            warehouse="MAIN_WH",
            aisle="A1",
            row="R2",
            shelf="S3",
            bin="B04",
            user=self.user,
            source="MANUAL"
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["quantity_added"], 50)
        self.assertEqual(result["current_ledger_quantity"], 50)

        ledger = InventoryLedger.objects.get(product=self.product, batch_id="BATCH-2026-A")
        self.assertEqual(ledger.quantity, 50)
        self.assertEqual(ledger.location.shelf, "S3")

        # Verify TransactionLog was created
        log = TransactionLog.objects.filter(product=self.product, transaction_type='INTAKE').latest('timestamp')
        self.assertEqual(log.quantity_change, 50)
        self.assertEqual(log.user, self.user)

    def test_02_transaction_log_immutability(self):
        InventoryEngine.intake(
            sku=self.product.sku,
            quantity=10,
            batch_id="BATCH-IMMUTABLE",
            mfg_date=self.today,
            expiry_date=self.today + timedelta(days=100),
            warehouse="WH1", aisle="A", row="1", shelf="1"
        )
        log = TransactionLog.objects.first()
        
        # Attempt update
        log.quantity_change = 999
        with self.assertRaises(ValueError) as ctx:
            log.save()
        self.assertIn("immutable", str(ctx.exception).lower())

        # Attempt delete
        with self.assertRaises(ValueError) as ctx:
            log.delete()
        self.assertIn("immutable", str(ctx.exception).lower())

    def test_03_fefo_outtake_closest_expiry_and_shelf_guidance(self):
        # Batch 1: Expires in 10 days, Shelf S1, Qty 10
        InventoryEngine.intake(
            sku=self.product.sku, quantity=10, batch_id="EXP-10D",
            mfg_date=self.today - timedelta(days=20),
            expiry_date=self.today + timedelta(days=10),
            warehouse="WH1", aisle="A", row="1", shelf="S1", bin="B1"
        )
        # Batch 2: Expires in 30 days, Shelf S2, Qty 20
        InventoryEngine.intake(
            sku=self.product.sku, quantity=20, batch_id="EXP-30D",
            mfg_date=self.today - timedelta(days=10),
            expiry_date=self.today + timedelta(days=30),
            warehouse="WH1", aisle="A", row="1", shelf="S2", bin="B2"
        )

        # Outtake 5: Must come from Batch 1 (EXP-10D) at Shelf S1
        out_res = InventoryEngine.outtake(sku=self.product.sku, quantity=5)
        self.assertEqual(out_res["total_deducted"], 5)
        self.assertEqual(len(out_res["pick_directions"]), 1)
        pick = out_res["pick_directions"][0]
        self.assertEqual(pick["batch_id"], "EXP-10D")
        self.assertEqual(pick["shelf"], "S1")
        self.assertEqual(pick["quantity_picked"], 5)

        # Ledger check
        ledger1 = InventoryLedger.objects.get(batch_id="EXP-10D")
        self.assertEqual(ledger1.quantity, 5)

    def test_04_fefo_multi_shelf_split(self):
        # Batch 1: Expires in 5 days, Shelf S1, Qty 4
        InventoryEngine.intake(
            sku=self.product.sku, quantity=4, batch_id="EXP-5D",
            mfg_date=self.today - timedelta(days=30),
            expiry_date=self.today + timedelta(days=5),
            warehouse="WH1", aisle="A", row="1", shelf="S1"
        )
        # Batch 2: Expires in 15 days, Shelf S2, Qty 10
        InventoryEngine.intake(
            sku=self.product.sku, quantity=10, batch_id="EXP-15D",
            mfg_date=self.today - timedelta(days=10),
            expiry_date=self.today + timedelta(days=15),
            warehouse="WH1", aisle="A", row="1", shelf="S2"
        )

        # Outtake 6: Should take 4 from EXP-5D (Shelf S1) and 2 from EXP-15D (Shelf S2)
        out_res = InventoryEngine.outtake(sku=self.product.sku, quantity=6)
        self.assertEqual(len(out_res["pick_directions"]), 2)
        
        self.assertEqual(out_res["pick_directions"][0]["batch_id"], "EXP-5D")
        self.assertEqual(out_res["pick_directions"][0]["quantity_picked"], 4)
        self.assertEqual(out_res["pick_directions"][0]["shelf"], "S1")

        self.assertEqual(out_res["pick_directions"][1]["batch_id"], "EXP-15D")
        self.assertEqual(out_res["pick_directions"][1]["quantity_picked"], 2)
        self.assertEqual(out_res["pick_directions"][1]["shelf"], "S2")

        self.assertEqual(InventoryLedger.objects.get(batch_id="EXP-5D").quantity, 0)
        self.assertEqual(InventoryLedger.objects.get(batch_id="EXP-15D").quantity, 8)

    def test_05_fefo_excludes_expired_stock(self):
        # Batch 1: Expired yesterday, Qty 20
        InventoryEngine.intake(
            sku=self.product.sku, quantity=20, batch_id="EXPIRED-BATCH",
            mfg_date=self.today - timedelta(days=100),
            expiry_date=self.today - timedelta(days=1),
            warehouse="WH1", aisle="A", row="1", shelf="S-EXP"
        )
        # Batch 2: Fresh, expires in 60 days, Qty 3
        InventoryEngine.intake(
            sku=self.product.sku, quantity=3, batch_id="FRESH-BATCH",
            mfg_date=self.today,
            expiry_date=self.today + timedelta(days=60),
            warehouse="WH1", aisle="A", row="1", shelf="S-FRESH"
        )

        # Requesting 4 should fail because only 3 unexpired are available (expired 20 are excluded)
        with self.assertRaises(InsufficientStockError):
            InventoryEngine.outtake(sku=self.product.sku, quantity=4)

        # Requesting 3 succeeds from fresh batch
        out_res = InventoryEngine.outtake(sku=self.product.sku, quantity=3)
        self.assertEqual(out_res["pick_directions"][0]["batch_id"], "FRESH-BATCH")

    def test_06_manual_adjustment_mandatory_reason_code(self):
        res = InventoryEngine.intake(
            sku=self.product.sku, quantity=25, batch_id="ADJUST-TEST",
            mfg_date=self.today, expiry_date=self.today + timedelta(days=90),
            warehouse="WH1", aisle="A", row="1", shelf="S1"
        )
        loc_id = res["location_id"]

        # Missing or empty reason code MUST fail
        with self.assertRaises(InvalidAdjustmentError):
            InventoryEngine.adjust(
                sku=self.product.sku, batch_id="ADJUST-TEST", location_id=loc_id,
                quantity_change=-2, reason_code=""
            )

        with self.assertRaises(InvalidAdjustmentError):
            InventoryEngine.adjust(
                sku=self.product.sku, batch_id="ADJUST-TEST", location_id=loc_id,
                quantity_change=-2, reason_code="   "
            )

        # Valid adjustment for influencer PR
        adj_res = InventoryEngine.adjust(
            sku=self.product.sku, batch_id="ADJUST-TEST", location_id=loc_id,
            quantity_change=-5, reason_code="INFLUENCER_SEEDING", user=self.user
        )
        self.assertEqual(adj_res["new_balance"], 20)

        log = TransactionLog.objects.filter(transaction_type='ADJUST').latest('timestamp')
        self.assertEqual(log.quantity_change, -5)
        self.assertEqual(log.reason_code, "INFLUENCER_SEEDING")

        # Disallow negative ledger balance
        with self.assertRaises(InsufficientStockError):
            InventoryEngine.adjust(
                sku=self.product.sku, batch_id="ADJUST-TEST", location_id=loc_id,
                quantity_change=-50, reason_code="DAMAGED_LEAKAGE"
            )

    def test_07_bogo_bundle_order_processing(self):
        # Stock base product with 10 units
        InventoryEngine.intake(
            sku=self.product.sku, quantity=10, batch_id="BOGO-BASE-BATCH",
            mfg_date=self.today, expiry_date=self.today + timedelta(days=180),
            warehouse="WH1", aisle="A", row="1", shelf="S10"
        )

        # Order arrives from SHOPIFY with 2 of promotional BOGO SKU (multiplier is 2, so 4 base units deducted)
        order_payload = {
            "order_id": "ORD-SHOPIFY-999",
            "source": "SHOPIFY",
            "items": [
                {"sku": "PROMO-BOGO-LIPSTICK", "quantity": 2}
            ]
        }

        order_res = InventoryEngine.process_order(
            order_id=order_payload["order_id"],
            source=order_payload["source"],
            items=order_payload["items"],
            user=self.user
        )

        item = order_res["fulfilled_items"][0]
        self.assertTrue(item["is_bundle"])
        self.assertEqual(item["quantity_multiplier"], 2)
        self.assertEqual(item["actual_quantity_deducted"], 4)
        self.assertEqual(item["base_sku"], self.product.sku)

        # Ledger check: 10 - 4 = 6 remaining
        ledger = InventoryLedger.objects.get(batch_id="BOGO-BASE-BATCH")
        self.assertEqual(ledger.quantity, 6)

    def test_08_inventory_summary_with_expired_stock_breakdown(self):
        # 15 expired
        InventoryEngine.intake(
            sku=self.product.sku, quantity=15, batch_id="EXPIRED-SUMM",
            mfg_date=self.today - timedelta(days=120),
            expiry_date=self.today - timedelta(days=5),
            warehouse="WH1", aisle="A", row="1", shelf="S1"
        )
        # 35 active
        InventoryEngine.intake(
            sku=self.product.sku, quantity=35, batch_id="ACTIVE-SUMM",
            mfg_date=self.today,
            expiry_date=self.today + timedelta(days=90),
            warehouse="WH1", aisle="A", row="1", shelf="S2"
        )

        summary = InventoryEngine.get_inventory_summary(self.product.sku)
        self.assertEqual(summary["total_quantity"], 50)
        self.assertEqual(summary["expired_quantity"], 15)
        self.assertEqual(summary["sellable_quantity"], 35)

    def test_09_channel_rate_limiter_and_celery_task(self):
        # Verify rate limiter allows initial burst
        allowed = ChannelRateLimiter.acquire("SHOPIFY", rate=2.0, burst=2)
        self.assertTrue(allowed)

        # Stock up and trigger Celery task
        InventoryEngine.intake(
            sku=self.product.sku, quantity=10, batch_id="CELERY-TEST",
            mfg_date=self.today, expiry_date=self.today + timedelta(days=100),
            warehouse="WH1", aisle="A", row="1", shelf="S1"
        )

        task_result = sync_channel_inventory_task(sku=self.product.sku)
        self.assertIn("SHOPIFY", task_result)
        self.assertIn("AMAZON", task_result)
        self.assertIn("FLIPKART", task_result)
        self.assertEqual(task_result["SHOPIFY"]["status"], "SUCCESS")
