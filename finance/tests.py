from datetime import date, timedelta
from decimal import Decimal
import io
import zipfile

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from inventory.models import InventoryLedger, Product, Batch
from inventory.services import InventoryEngine, WholesalerService
from .models import (
    ApprovalStatus,
    BatchExpiryWriteOff,
    ChannelSkuMapping,
    ExpenseBucket,
    FactOrderUnitEconomics,
    FinancialAuditLog,
    FinancialTreasuryConfig,
    LorryReceipt,
    LossAndLeakageRecord,
    LossCategory,
    ManualRevenueEntry,
    MarketingAndOpexEntry,
    ReconciliationStatus,
    SalesChannel,
)
from .services import OmnichannelIngestionService, WaterfallAnalyticsService


class FinanceCommandCenterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.today = timezone.now().date()

        self.admin_user = User.objects.create_user(username="founder_admin", password="pw", is_staff=True)
        self.maker_user = User.objects.create_user(username="fin_analyst", password="pw", is_staff=False)

        self.product = Product.objects.create(
            sku="PURA-SERUM-30",
            name="Purastone Mineral Radiance Serum 30ml",
            base_price=Decimal("999.00"),
            base_cost=Decimal("220.00"),
            default_b2b_price=Decimal("550.00"),
        )
        InventoryEngine.intake(
            sku=self.product.sku,
            quantity=10,
            batch_id="SERUM-B1",
            mfg_date=self.today - timedelta(days=40),
            expiry_date=self.today + timedelta(days=20),
            warehouse="CENTRAL_WH",
            aisle="A1",
            row="R1",
            shelf="S1",
        )
        InventoryEngine.intake(
            sku=self.product.sku,
            quantity=50,
            batch_id="SERUM-B2",
            mfg_date=self.today - timedelta(days=5),
            expiry_date=self.today + timedelta(days=200),
            warehouse="CENTRAL_WH",
            aisle="A1",
            row="R1",
            shelf="S2",
        )

        ChannelSkuMapping.objects.create(
            internal_sku=self.product,
            channel=SalesChannel.AMAZON,
            external_product_id="B09PURASTONE1",
            external_sku_code="AMZ-SERUM-30",
            default_platform_commission_pct=Decimal("18.00"),
            default_packaging_cost_per_unit=Decimal("20.00"),
            default_inward_freight_per_unit=Decimal("10.00"),
        )
        ChannelSkuMapping.objects.create(
            internal_sku=self.product,
            channel=SalesChannel.SHOPIFY_D2C,
            external_product_id="SHP-VAR-991",
            external_sku_code="SHP-SERUM-30",
            default_platform_commission_pct=Decimal("0.00"),
            default_packaging_cost_per_unit=Decimal("20.00"),
            default_inward_freight_per_unit=Decimal("10.00"),
        )

        FinancialTreasuryConfig.objects.create(
            pk=1,
            cash_in_bank_balance=Decimal("1000000.00"),
            monthly_interest_expense=Decimal("0.00"),
            effective_tax_rate_pct=Decimal("0.00"),
        )

    def test_01_strict_6_tier_waterfall_decimal_math(self):
        """Verifies exact Decimal arithmetic across GMV -> Net Rev -> CM1 -> CM2 -> CM3 -> EBITDA -> PAT."""
        econ = FactOrderUnitEconomics.objects.create(
            order_date=self.today,
            channel=SalesChannel.SHOPIFY_D2C,
            external_order_ref="SHP-1001",
            reconciliation_status=ReconciliationStatus.RECONCILED,
            primary_sku=self.product,
            gross_sales_gmv=Decimal("1180.00"),
            gst_tax_amount=Decimal("180.00"),
            discounts_and_rebates=Decimal("50.00"),
            returns_and_rto_reversal=Decimal("0.00"),
            batch_formulation_cogs=Decimal("220.00"),
            primary_packaging_cost=Decimal("20.00"),
            inward_freight_overhead=Decimal("10.00"),
            platform_commission_fees=Decimal("0.00"),
            payment_gateway_fees=Decimal("25.00"),
            outbound_freight_cost=Decimal("75.00"),
            rto_reverse_freight_cost=Decimal("0.00"),
            master_carton_and_pick_pack=Decimal("15.00"),
            transit_breakage_cost=Decimal("0.00"),
            actual_settled_payout=Decimal("1030.00"),
            amount_collected=Decimal("1030.00"),
        )
        # Net Rev = 1180 - 180 - 50 - 0 = 950.00
        self.assertEqual(econ.net_revenue, Decimal("950.00"))
        # CM1 = 950 - (220 + 20 + 10) = 700.00
        self.assertEqual(econ.cm1_amount, Decimal("700.00"))
        # CM2 = 700 - (0 + 25 + 75 + 0 + 15 + 0) = 585.00
        self.assertEqual(econ.cm2_amount, Decimal("585.00"))

        # Add 10-day Marketing entry overlapping today by 1 day -> prorated 1000 / 10 = 100.00
        MarketingAndOpexEntry.objects.create(
            period_start_date=self.today,
            period_end_date=self.today + timedelta(days=9),
            bucket=ExpenseBucket.META_GOOGLE_ADS,
            target_channel=SalesChannel.SHOPIFY_D2C,
            amount_exclusive_gst=Decimal("1000.00"),
            vendor_or_platform_name="Meta Ads",
            approval_status=ApprovalStatus.APPROVED,
            created_by=self.admin_user,
            approved_by=self.admin_user,
        )
        # Add 1-day Fixed OPEX -> 150.00
        MarketingAndOpexEntry.objects.create(
            period_start_date=self.today,
            period_end_date=self.today,
            bucket=ExpenseBucket.PAYROLL_SALARIES,
            amount_exclusive_gst=Decimal("150.00"),
            vendor_or_platform_name="Payroll",
            approval_status=ApprovalStatus.APPROVED,
            created_by=self.admin_user,
            approved_by=self.admin_user,
        )
        # Non-order QC wastage loss -> 35.00
        LossAndLeakageRecord.objects.create(
            incurred_date=self.today,
            category=LossCategory.QC_LAB_REJECTION,
            total_loss_amount=Decimal("35.00"),
            reason_notes="Lab sample discard",
            approval_status=ApprovalStatus.APPROVED,
            created_by=self.admin_user,
        )

        summary = WaterfallAnalyticsService.get_command_center_summary(self.today, self.today)
        kpis = summary["kpis"]
        self.assertEqual(Decimal(kpis["net_revenue"]), Decimal("950.00"))
        self.assertEqual(Decimal(kpis["cm1"]), Decimal("700.00"))
        self.assertEqual(Decimal(kpis["cm2"]), Decimal("585.00"))
        # CM3 = 585 - 100 = 485.00
        self.assertEqual(Decimal(kpis["cm3"]), Decimal("485.00"))
        # EBITDA = 485 - 150 - 35 = 300.00
        self.assertEqual(Decimal(kpis["ebitda"]), Decimal("300.00"))
        self.assertEqual(Decimal(kpis["net_profit"]), Decimal("300.00"))

    def test_02_100_percent_rto_order_zero_division_and_negative_cm2_alert(self):
        """100% RTO orders yield Net Revenue <= 0, safe 0.00 margin %, negative CM2, and trigger anomaly alert."""
        econ = OmnichannelIngestionService.ingest_provisional_order(
            channel=SalesChannel.AMAZON,
            external_order_ref="AMZ-RTO-100",
            order_date=self.today,
            items=[{"external_product_id": "B09PURASTONE1", "quantity": 1, "line_gross": "1180.00"}],
            gross_sales_gmv=Decimal("1180.00"),
            gst_tax_amount=Decimal("180.00"),
            discounts_and_rebates=Decimal("0.00"),
        )
        self.assertEqual(econ.reconciliation_status, ReconciliationStatus.PROVISIONAL)

        # Settlement comes back as 100% RTO with unreturned inventory and reverse freight
        reconciled = OmnichannelIngestionService.reconcile_settlement(
            channel=SalesChannel.AMAZON,
            external_order_ref="AMZ-RTO-100",
            actual_settled_payout=Decimal("-180.00"),
            settlement_utr="AMZ-UTR-9901",
            platform_commission_fees=Decimal("0.00"),
            outbound_freight_cost=Decimal("90.00"),
            rto_reverse_freight_cost=Decimal("90.00"),
            returns_and_rto_reversal=Decimal("1000.00"),
            is_rto=True,
            rto_inventory_returned=False,
        )
        self.assertEqual(reconciled.net_revenue, Decimal("0.00"))
        self.assertEqual(reconciled.cm1_margin_pct, Decimal("0.00"))
        self.assertEqual(reconciled.cm2_margin_pct, Decimal("0.00"))
        self.assertLess(reconciled.cm2_amount, Decimal("0.00"))
        self.assertEqual(reconciled.reconciliation_status, ReconciliationStatus.DISPUTED)
        # Unreturned RTO loss recorded
        self.assertTrue(
            LossAndLeakageRecord.objects.filter(
                linked_order_econ=reconciled, category=LossCategory.UNRETURNED_RTO_LOSS
            ).exists()
        )
        summary = WaterfallAnalyticsService.get_command_center_summary(self.today, self.today)
        anomaly_types = [a["type"] for a in summary["anomalies"]]
        self.assertIn("NEGATIVE_CM2", anomaly_types)
        self.assertIn("HIGH_RTO_SPIKE", anomaly_types)

    def test_03_b2b_order_tms_lr_pod_and_multi_batch_fefo_split(self):
        """
        Tests B2B confirmation signal -> multi-batch FEFO COGS splits (10 from SERUM-B1 + 5 from SERUM-B2)
        and LorryReceipt POD verification transitioning PROVISIONAL -> RECONCILED + logging breakage without double-counting.
        """
        parent = WholesalerService.onboard_parent("Glow Spa", "27AABCG1111F1Z1", "glow@spa.in")
        WholesalerService.approve_parent(parent.id)
        child = WholesalerService.create_child_account(
            parent_id=parent.id,
            branch_name="Glow South",
            store_id="GLOW-01",
            shipping_address="Mumbai",
            contact_person="Meera",
            username="glow_south",
        )
        # Order 15 units -> splits 10 from SERUM-B1 + 5 from SERUM-B2 via FEFO!
        order = WholesalerService.create_draft_order(
            child_id=child.id,
            items=[{"sku": self.product.sku, "quantity": 15, "unit_price": "550.00", "gst_percentage": "18.00"}],
        )
        # Partial B2B discount / credit note adjustment within margin
        WholesalerService.apply_discount(str(order.id), "FLAT", 250.00)
        WholesalerService.confirm_order(str(order.id), user=self.admin_user)

        econ = FactOrderUnitEconomics.objects.get(wholesale_order=order)
        self.assertEqual(econ.reconciliation_status, ReconciliationStatus.PROVISIONAL)
        self.assertEqual(econ.discounts_and_rebates, Decimal("250.00"))
        # Multi-batch allocations recorded
        allocs = list(econ.batch_allocations.order_by("batch__expiry_date"))
        self.assertEqual(len(allocs), 2)
        self.assertEqual(allocs[0].batch.batch_id, "SERUM-B1")
        self.assertEqual(allocs[0].units_dispatched, 10)
        self.assertEqual(allocs[1].batch.batch_id, "SERUM-B2")
        self.assertEqual(allocs[1].units_dispatched, 5)

        # Attach LorryReceipt with Prepaid freight & POD damage -> RECONCILED + TRANSIT_LR_BREAKAGE
        lr = LorryReceipt.objects.create(
            lr_number="LR-2026-881",
            wholesale_order=order,
            transporter_name="SafeExpress Logistics",
            freight_mode="PAID_PREPAID",
            freight_amount=Decimal("600.00"),
            ancillary_packaging_cost=Decimal("120.00"),
            pod_status="DAMAGED",
            pod_damage_units=1,
            pod_damage_cost=Decimal("220.00"),
            pod_verified_at=timezone.now(),
        )
        econ.refresh_from_db()
        self.assertEqual(econ.reconciliation_status, ReconciliationStatus.RECONCILED)
        self.assertEqual(econ.outbound_freight_cost, Decimal("600.00"))
        self.assertEqual(econ.transit_breakage_cost, Decimal("220.00"))
        self.assertTrue(
            LossAndLeakageRecord.objects.filter(
                linked_order_econ=econ, category=LossCategory.TRANSIT_LR_BREAKAGE
            ).exists()
        )
        # Ensure linked TRANSIT_LR_BREAKAGE is NOT double-counted in EBITDA non_order_losses
        summary = WaterfallAnalyticsService.get_command_center_summary(self.today, self.today)
        self.assertEqual(Decimal(summary["waterfall_detail"]["non_order_losses"]), Decimal("0.00"))
        self.assertEqual(Decimal(summary["kpis"]["total_losses"]), Decimal("220.00"))

    def test_04_batch_expiry_writeoff_hook(self):
        """BatchExpiryWriteOff signal automatically logs Approved FEFO_BATCH_EXPIRY loss."""
        batch = Batch.objects.get(batch_id="SERUM-B1")
        BatchExpiryWriteOff.objects.create(
            batch=batch,
            writeoff_date=self.today,
            units_written_off=4,
            unit_cost=Decimal("220.00"),
            notes="Damaged seal prior to dispatch",
            created_by=self.admin_user,
        )
        loss = LossAndLeakageRecord.objects.get(affected_batch=batch, category=LossCategory.FEFO_BATCH_EXPIRY)
        self.assertEqual(loss.total_loss_amount, Decimal("880.00"))
        self.assertEqual(loss.approval_status, ApprovalStatus.APPROVED)

    def test_05_manual_entry_maker_checker_rbac_and_fefo_stock_deduction(self):
        """Non-Admin Maker cannot approve (403); Admin approves, deducts FEFO stock, and writes immutable AuditLog."""
        res = self.client.post(
            reverse("fin_manual_sales"),
            data={
                "sale_date": self.today.isoformat(),
                "reference_number": "EXPO-BKC-01",
                "customer_or_store_name": "Nykaa Pop-Up Bandra",
                "sku": self.product.sku,
                "quantity": 3,
                "gross_amount": "2997.00",
                "gst_amount": "457.17",
                "discount_amount": "0.00",
                "manual_freight_and_packing": "100.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        entry_id = res.data["id"]
        self.assertEqual(res.data["approval_status"], ApprovalStatus.PENDING)

        # Maker / non-staff user forbidden from approving
        self.client.force_authenticate(user=self.maker_user)
        forbidden_res = self.client.post(
            reverse("fin_approval_decision", kwargs={"entity_type": "manual-sale", "entry_id": entry_id}),
            data={"action": "APPROVE"},
            format="json",
        )
        self.assertEqual(forbidden_res.status_code, 403)

        # Also test header-based non-admin guard
        self.client.force_authenticate(user=None)
        hdr_forbidden = self.client.post(
            reverse("fin_approval_decision", kwargs={"entity_type": "manual-sale", "entry_id": entry_id}),
            data={"action": "APPROVE"},
            format="json",
            HTTP_X_ERP_ROLE="FINANCE_ANALYST",
        )
        self.assertEqual(hdr_forbidden.status_code, 403)

        # Admin approves -> FEFO stock deducted (SERUM-B1 drops from 10 to 7) & FactOrderUnitEconomics posted
        self.client.force_authenticate(user=self.admin_user)
        ok_res = self.client.post(
            reverse("fin_approval_decision", kwargs={"entity_type": "manual-sale", "entry_id": entry_id}),
            data={"action": "APPROVE"},
            format="json",
        )
        self.assertEqual(ok_res.status_code, 200)
        b1_ledger = InventoryLedger.objects.get(batch__batch_id="SERUM-B1")
        self.assertEqual(b1_ledger.quantity, 7)
        econ = FactOrderUnitEconomics.objects.get(external_order_ref="EXPO-BKC-01")
        self.assertEqual(econ.batch_formulation_cogs, Decimal("660.00"))  # 3 * 220

        # Immutable AuditLog check
        audit = FinancialAuditLog.objects.filter(entity_id=entry_id, action="APPROVE").first()
        self.assertIsNotNone(audit)
        with self.assertRaises(ValueError):
            audit.notes = "Tampered"
            audit.save()
        with self.assertRaises(ValueError):
            audit.delete()

    def test_06_multi_batch_cost_split_explorer_csv_import_and_exports(self):
        """Tests explicit multi-batch cost splits, bulk CSV import, working capital, PDF & XLSX exports."""
        OmnichannelIngestionService.ingest_provisional_order(
            channel=SalesChannel.SHOPIFY_D2C,
            external_order_ref="SHP-SPLIT-01",
            order_date=self.today,
            items=[{
                "external_product_id": "SHP-VAR-991",
                "quantity": 10,
                "line_gross": "9990.00",
                "batch_splits": [
                    {"batch_id": "SERUM-B1", "quantity": 4, "unit_cost": "205.00"},
                    {"batch_id": "SERUM-B2", "quantity": 6, "unit_cost": "235.00"},
                ],
            }],
            gross_sales_gmv=Decimal("9990.00"),
            gst_tax_amount=Decimal("1523.90"),
        )
        econ = FactOrderUnitEconomics.objects.get(external_order_ref="SHP-SPLIT-01")
        # 4*205 + 6*235 = 820 + 1410 = 2230.00
        self.assertEqual(econ.batch_formulation_cogs, Decimal("2230.00"))

        # Unit economics explorer shows batch variance
        exp_res = self.client.get(reverse("fin_unit_economics"), {"preset": "MTD"})
        self.assertEqual(exp_res.status_code, 200)
        self.assertGreaterEqual(len(exp_res.data["sku_rankings"]), 1)
        self.assertEqual(len(exp_res.data["batch_variance"]), 2)

        # Bulk CSV OPEX import
        csv_body = (
            "period_start_date,period_end_date,bucket,target_channel,amount_exclusive_gst,vendor_or_platform_name\n"
            f"{self.today.isoformat()},{self.today.isoformat()},META_GOOGLE_ADS,SHOPIFY_D2C,500.00,Meta Campaign\n"
        )
        csv_res = self.client.post(
            reverse("fin_import_csv"),
            data={"type": "opex", "csv_content": csv_body},
            format="json",
        )
        self.assertEqual(csv_res.status_code, 201)
        self.assertEqual(csv_res.data["count"], 1)

        # Refresh materialized views / cache
        ref_res = self.client.post(reverse("fin_refresh_views"))
        self.assertEqual(ref_res.status_code, 200)

        # Working capital & runway check
        wc_res = self.client.get(reverse("fin_working_capital"))
        self.assertEqual(wc_res.status_code, 200)
        self.assertIn("runway_months", wc_res.data["runway"])

        # Exports: Boardroom PDF, CA XLSX, CA CSV
        pdf_res = self.client.get(reverse("fin_export_pdf"))
        self.assertEqual(pdf_res.status_code, 200)
        self.assertTrue(pdf_res.content.startswith(b"%PDF"))

        xlsx_res = self.client.get(reverse("fin_export_xlsx"))
        self.assertEqual(xlsx_res.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(xlsx_res.content)) as zf:
            self.assertIn("xl/worksheets/sheet1.xml", zf.namelist())
            self.assertIn("xl/worksheets/sheet4.xml", zf.namelist())

        csv_exp = self.client.get(reverse("fin_export_csv"))
        self.assertEqual(csv_exp.status_code, 200)
        self.assertIn("SHP-SPLIT-01", csv_exp.content.decode("utf-8"))

