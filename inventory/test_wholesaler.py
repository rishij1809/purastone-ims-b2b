from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from .models import (
    Product, Batch, Location, InventoryLedger, TransactionLog,
    WholesalerParent, WholesalerChild, WholesaleOrder, WholesaleOrderItem, Invoice
)
from .services import InventoryEngine, WholesalerService
from .exceptions import InsufficientStockError, NegativeMarginError
from .tasks import generate_invoice_pdf_task


class WholesalerModuleTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

        # Shared Product Master with COGS and B2B Base Price
        self.product = Product.objects.create(
            sku="PURA-ALUM-ROLLON-100",
            name="Purastone Natural Alum Roll-On 100ml",
            base_price=Decimal("749.00"),      # B2C
            base_cost=Decimal("250.00"),       # COGS
            default_b2b_price=Decimal("450.00") # B2B Base Price
        )

        # Pre-stock warehouse with 2 batches (FEFO candidate & future batch)
        InventoryEngine.intake(
            sku=self.product.sku,
            quantity=20,
            batch_id="BATCH-NEAR",
            mfg_date=self.today - timedelta(days=50),
            expiry_date=self.today + timedelta(days=20),
            warehouse="CENTRAL_WH", aisle="A1", row="R1", shelf="S01", bin="B01"
        )
        InventoryEngine.intake(
            sku=self.product.sku,
            quantity=80,
            batch_id="BATCH-FUTURE",
            mfg_date=self.today - timedelta(days=10),
            expiry_date=self.today + timedelta(days=200),
            warehouse="CENTRAL_WH", aisle="A1", row="R1", shelf="S02", bin="B02"
        )

    def test_01_master_onboarding_and_child_generation(self):
        # 1. Onboarding sets status to PENDING
        parent = WholesalerService.onboard_parent(
            name="Aura Wellness Retail Pvt Ltd",
            gstin="27AABCA1234F1Z5",
            master_email="procurement@aurawellness.com"
        )
        self.assertEqual(parent.status, "PENDING")

        # Duplicate GSTIN fails
        with self.assertRaises(ValueError):
            WholesalerService.onboard_parent(
                name="Duplicate Retail",
                gstin="27AABCA1234F1Z5",
                master_email="other@aura.com"
            )

        # Cannot spawn child for unapproved parent
        with self.assertRaises(ValueError):
            WholesalerService.create_child_account(
                parent_id=parent.id,
                branch_name="Bandra Flagship",
                store_id="AURA-MUM-01",
                shipping_address="Linking Rd, Bandra West, Mumbai",
                contact_person="Rajesh Sharma",
                username="aura_bandra"
            )

        # 2. Admin approval
        WholesalerService.approve_parent(parent.id)
        parent.refresh_from_db()
        self.assertEqual(parent.status, "APPROVED")

        # 3. Spawn child branch
        child = WholesalerService.create_child_account(
            parent_id=parent.id,
            branch_name="Bandra Flagship",
            store_id="AURA-MUM-01",
            shipping_address="Linking Rd, Bandra West, Mumbai",
            contact_person="Rajesh Sharma",
            username="aura_bandra",
            password="SecurePass@123"
        )
        self.assertEqual(child.parent, parent)
        self.assertEqual(child.user.username, "aura_bandra")

    def test_02_draft_order_locks_base_cost_immutably(self):
        parent = WholesalerService.onboard_parent(
            name="Zenith Spas", gstin="29XYZPA9999K1Z2", master_email="ops@zenithspas.com"
        )
        WholesalerService.approve_parent(parent.id)
        child = WholesalerService.create_child_account(
            parent_id=parent.id, branch_name="Indiranagar Branch",
            store_id="ZEN-BLR-01", shipping_address="100ft Rd, Bangalore",
            contact_person="Kavita Rao", username="zen_blr"
        )

        # Place draft order for 10 units
        order = WholesalerService.create_draft_order(
            child_id=child.id,
            items=[{"sku": self.product.sku, "quantity": 10}]
        )

        item = order.items.first()
        self.assertEqual(item.locked_base_cost, Decimal("250.00"))
        self.assertEqual(item.locked_b2b_price, Decimal("450.00"))
        self.assertEqual(order.subtotal, Decimal("4500.00"))
        self.assertEqual(order.total_cogs, Decimal("2500.00"))
        self.assertEqual(order.final_value, Decimal("4500.00"))
        self.assertEqual(order.net_profit, Decimal("2000.00"))

        # Mutate Product catalog cost & price
        self.product.base_cost = Decimal("320.00")
        self.product.default_b2b_price = Decimal("550.00")
        self.product.save()

        # Re-fetch order item; locked cost and price must remain completely unchanged
        item.refresh_from_db()
        self.assertEqual(item.locked_base_cost, Decimal("250.00"))
        self.assertEqual(item.locked_b2b_price, Decimal("450.00"))

    def test_03_discount_engine_prevents_negative_margins(self):
        parent = WholesalerService.onboard_parent(
            name="Apex Luxury Stores", gstin="07AAAAA1111A1Z1", master_email="b2b@apexluxury.com"
        )
        WholesalerService.approve_parent(parent.id)
        child = WholesalerService.create_child_account(
            parent_id=parent.id, branch_name="CP Outlet",
            store_id="APX-DEL-01", shipping_address="Connaught Place, New Delhi",
            contact_person="Amitabh Verma", username="apex_del"
        )

        order = WholesalerService.create_draft_order(
            child_id=child.id,
            items=[{"sku": self.product.sku, "quantity": 10}]
        )
        # Subtotal = 4,500.00, Total COGS = 2,500.00. Max discount = 2,000.00

        # Attempt discount of ₹2,100 (breaches floor, final value = 2,400 < 2,500 COGS)
        with self.assertRaises(NegativeMarginError):
            WholesalerService.apply_discount(
                order_id=str(order.id),
                discount_type="FLAT",
                discount_value=2100.00
            )

        # Attempt 50% discount (breaches floor: 50% of 4,500 = 2,250 > 2,000 max discount)
        with self.assertRaises(NegativeMarginError):
            WholesalerService.apply_discount(
                order_id=str(order.id),
                discount_type="PERCENTAGE",
                discount_value=50.0
            )

        # Apply valid 20% discount (20% of 4,500 = 900.00, final = 3,600.00 > 2,500 COGS)
        discounted_order = WholesalerService.apply_discount(
            order_id=str(order.id),
            discount_type="PERCENTAGE",
            discount_value=20.0
        )
        self.assertEqual(discounted_order.status, "DISCOUNT_APPLIED")
        self.assertEqual(discounted_order.discount_amount, Decimal("900.00"))
        self.assertEqual(discounted_order.final_value, Decimal("3600.00"))
        self.assertEqual(discounted_order.net_profit, Decimal("1100.00"))

    def test_04_order_confirmation_triggers_fefo_outtake_and_invoice(self):
        parent = WholesalerService.onboard_parent(
            name="Veda Salons", gstin="33BBBBB2222B1Z2", master_email="stock@vedasalons.com"
        )
        WholesalerService.approve_parent(parent.id)
        child = WholesalerService.create_child_account(
            parent_id=parent.id, branch_name="Chennai Central",
            store_id="VED-CHE-01", shipping_address="Anna Salai, Chennai",
            contact_person="Priya Raman", username="veda_chennai"
        )

        # Order 25 units: Stock has 20 in BATCH-NEAR and 80 in BATCH-FUTURE
        order = WholesalerService.create_draft_order(
            child_id=child.id,
            items=[{"sku": self.product.sku, "quantity": 25}]
        )

        confirm_res = WholesalerService.confirm_order(order_id=str(order.id))
        self.assertEqual(confirm_res["status"], "SUCCESS")

        order.refresh_from_db()
        self.assertEqual(order.status, "CONFIRMED")

        # Verify FEFO split: 20 picked from BATCH-NEAR, 5 picked from BATCH-FUTURE
        pick_dirs = confirm_res["pick_results"][0]["pick_directions"]
        self.assertEqual(len(pick_dirs), 2)
        self.assertEqual(pick_dirs[0]["batch_id"], "BATCH-NEAR")
        self.assertEqual(pick_dirs[0]["quantity_picked"], 20)
        self.assertEqual(pick_dirs[1]["batch_id"], "BATCH-FUTURE")
        self.assertEqual(pick_dirs[1]["quantity_picked"], 5)

        # Verify TransactionLog has source='WHOLESALE'
        wholesale_logs = TransactionLog.objects.filter(source="WHOLESALE")
        self.assertEqual(wholesale_logs.count(), 2)

        # Execute PDF invoice task
        task_res = generate_invoice_pdf_task(order_id=str(order.id))
        self.assertIn("pdf_url", task_res)
        invoice = Invoice.objects.get(order=order)
        self.assertTrue(invoice.pdf_url.endswith(".pdf"))

    def test_05_wholesaler_analytics_master_and_individual(self):
        parent = WholesalerService.onboard_parent(
            name="Luxe Retail Network", gstin="24CCCCC3333C1Z3", master_email="accounts@luxeretail.com"
        )
        WholesalerService.approve_parent(parent.id)
        child = WholesalerService.create_child_account(
            parent_id=parent.id, branch_name="Ahmedabad SG Highway",
            store_id="LUX-AMD-01", shipping_address="SG Highway, Ahmedabad",
            contact_person="Mehul Patel", username="luxe_ahmedabad"
        )

        # Order 10 units @ 450 = 4,500. COGS = 2,500. Discount = 500. Final = 4,000. Profit = 1,500.
        order = WholesalerService.create_draft_order(
            child_id=child.id,
            items=[{"sku": self.product.sku, "quantity": 10}]
        )
        WholesalerService.apply_discount(order_id=str(order.id), discount_type="FLAT", discount_value=500.00)
        WholesalerService.confirm_order(order_id=str(order.id))

        # Individual Wholesaler Analytics
        ind_analytics = WholesalerService.get_analytics(parent_id=parent.id)
        self.assertEqual(ind_analytics["total_revenue"], "4000.00")
        self.assertEqual(ind_analytics["total_cogs"], "2500.00")
        self.assertEqual(ind_analytics["net_profit"], "1500.00")
        # Yield = (1500 / 4000) * 100 = 37.5%
        self.assertEqual(ind_analytics["margin_yield_percentage"], 37.5)

        # Master Analytics
        master_analytics = WholesalerService.get_analytics()
        self.assertGreaterEqual(master_analytics["active_wholesalers_count"], 1)
        self.assertGreaterEqual(float(master_analytics["total_wholesale_revenue"]), 4000.00)
        self.assertGreaterEqual(float(master_analytics["total_wholesale_profit"]), 1500.00)
        self.assertGreater(master_analytics["system_net_profit_margin_percentage"], 0)

    def test_06_multi_product_draft_order_with_manual_price_and_gst(self):
        # Second product
        product2 = Product.objects.create(
            sku="PURA-MINERAL-MIST-150",
            name="Purastone Mineral Facial Mist 150ml",
            base_price=Decimal("649.00"),
            base_cost=Decimal("150.00"),
            default_b2b_price=Decimal("350.00")
        )

        parent = WholesalerService.onboard_parent(
            name="Multi Retail Mart", gstin="27MMMMM4444M1Z4", master_email="procure@multiretail.com"
        )
        WholesalerService.approve_parent(parent.id)
        child = WholesalerService.create_child_account(
            parent_id=parent.id, branch_name="Pune Main Store",
            store_id="MUL-PUN-01", shipping_address="FC Road, Pune",
            contact_person="Sunil Joshi", username="multi_pune"
        )

        # Multi-product order with manual unit_price and manual gst_percentage
        order = WholesalerService.create_draft_order(
            child_id=child.id,
            po_number="PO-MULTI-2026",
            notes="Handle with care - glass bottles",
            items=[
                {
                    "sku": self.product.sku,
                    "quantity": 10,
                    "unit_price": 480.00,
                    "gst_percentage": 18.00
                },
                {
                    "sku": product2.sku,
                    "quantity": 5,
                    "unit_price": 320.00,
                    "gst_percentage": 12.00
                }
            ]
        )

        self.assertEqual(order.po_number, "PO-MULTI-2026")
        self.assertEqual(order.subtotal, Decimal("6400.00")) # (10*480) + (5*320) = 4800 + 1600
        self.assertEqual(order.total_gst, Decimal("1056.00")) # 864 + 192
        self.assertEqual(order.grand_total, Decimal("7456.00"))
        self.assertEqual(order.total_cogs, Decimal("3250.00")) # (10*250) + (5*150)
        self.assertEqual(order.net_profit, Decimal("3150.00"))
        self.assertEqual(order.items.count(), 2)

        # Confirm order and verify PDF generation
        InventoryEngine.intake(
            sku=product2.sku, quantity=20, batch_id="BATCH-MIST-01",
            mfg_date=self.today - timedelta(days=10), expiry_date=self.today + timedelta(days=180),
            warehouse="CENTRAL_WH", aisle="A2", row="R1", shelf="S03", bin="B01"
        )
        confirm_res = WholesalerService.confirm_order(order_id=str(order.id))
        self.assertEqual(confirm_res["status"], "SUCCESS")
        order.refresh_from_db()
        self.assertEqual(order.status, "CONFIRMED")
        task_res = generate_invoice_pdf_task(order_id=str(order.id))
        self.assertIn("pdf_url", task_res)


