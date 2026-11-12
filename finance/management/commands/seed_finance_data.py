from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Batch, Product, WholesaleOrder
from finance.models import (
    ApprovalStatus,
    BatchExpiryWriteOff,
    ChannelSkuMapping,
    ExpenseBucket,
    FactOrderUnitEconomics,
    FinancialTreasuryConfig,
    LorryReceipt,
    LossAndLeakageRecord,
    LossCategory,
    ManualRevenueEntry,
    MarketingAndOpexEntry,
    SalesChannel,
)
from finance.services import InternalErpHookService, OmnichannelIngestionService
from finance.materialized import ensure_and_refresh_materialized_views


class Command(BaseCommand):
    help = "Seeds realistic Purastone Phase 6 CM1/CM2/CM3 & Omnichannel reconciliation data."

    def handle(self, *args, **options):
        today = timezone.now().date()
        admin, _ = User.objects.get_or_create(
            username="purastone_founder",
            defaults={"email": "founder@purastone.co", "is_staff": True, "is_superuser": True},
        )

        # 1. Treasury baseline
        FinancialTreasuryConfig.objects.update_or_create(
            pk=1,
            defaults={
                "cash_in_bank_balance": Decimal("3250000.00"),
                "monthly_interest_expense": Decimal("14500.00"),
                "effective_tax_rate_pct": Decimal("25.00"),
            },
        )

        rollon = Product.objects.filter(sku="PURA-ALUM-ROLLON-100").first()
        mist = Product.objects.filter(sku="PURA-MINERAL-MIST-150").first()
        lip = Product.objects.filter(sku="LIPSTICK-RUBY-01").first()
        if not rollon or not mist:
            self.stdout.write(self.style.WARNING("Core products missing; run seed_demo_data first."))
            return

        # 2. Channel SKU Mappings
        mappings = [
            (rollon, SalesChannel.SHOPIFY_D2C, "SHP-V-ROLL100", "SHP-PURA-ROLL-100", Decimal("0.00")),
            (mist, SalesChannel.SHOPIFY_D2C, "SHP-V-MIST150", "SHP-PURA-MIST-150", Decimal("0.00")),
            (rollon, SalesChannel.AMAZON, "B0D8PURA100", "AMZ-PURA-ROLL-100", Decimal("18.00")),
            (mist, SalesChannel.AMAZON, "B0D8PURA150", "AMZ-PURA-MIST-150", Decimal("18.00")),
            (rollon, SalesChannel.FLIPKART, "FSN-PURA-R100", "FK-PURA-ROLL-100", Decimal("16.50")),
            (lip or mist, SalesChannel.FLIPKART, "FSN-PURA-L001", "FK-LIP-01", Decimal("19.00")),
        ]
        for prod, ch, ext_id, ext_sku, comm in mappings:
            ChannelSkuMapping.objects.get_or_create(
                channel=ch,
                external_product_id=ext_id,
                defaults={
                    "internal_sku": prod,
                    "external_sku_code": ext_sku,
                    "default_platform_commission_pct": comm,
                    "default_packaging_cost_per_unit": Decimal("18.00"),
                    "default_inward_freight_per_unit": Decimal("7.50"),
                },
            )

        # 3. Sync existing confirmed B2B WholesaleOrders & attach TMS LorryReceipts
        confirmed_b2b = WholesaleOrder.objects.filter(status__in=["CONFIRMED", "FULFILLED"]).order_by("-created_at")
        for idx, b2b_order in enumerate(confirmed_b2b):
            econ = InternalErpHookService.sync_wholesale_order(b2b_order)
            lr_num = f"LR-2026-90{idx + 1}"
            if not LorryReceipt.objects.filter(lr_number=lr_num).exists():
                is_first = idx == 0
                LorryReceipt.objects.create(
                    lr_number=lr_num,
                    wholesale_order=b2b_order,
                    transporter_name="BlueDart Surface B2B" if is_first else "Delhivery Freight",
                    freight_mode="PAID_PREPAID",
                    freight_amount=Decimal("680.00") if is_first else Decimal("520.00"),
                    ancillary_packaging_cost=Decimal("140.00"),
                    transporter_payable_status="PENDING" if is_first else "PAID",
                    payable_due_date=today + timedelta(days=15),
                    pod_status="DAMAGED" if is_first else "CLEAN",
                    pod_damage_units=1 if is_first else 0,
                    pod_damage_cost=Decimal("250.00") if is_first else Decimal("0.00"),
                    pod_notes="1 glass alum bottle cracked on corner pallet" if is_first else "Clean POD signed",
                    pod_verified_at=timezone.now(),
                )
            if idx > 0 and econ:
                # Simulate overdue AR on older B2B order if any
                econ.order_date = today - timedelta(days=38)
                econ.payment_due_date = today - timedelta(days=8)
                econ.save()

        # 4. Shopify D2C Orders (Reconciled + Provisional)
        if not FactOrderUnitEconomics.objects.filter(external_order_ref="SHP-10421").exists():
            OmnichannelIngestionService.ingest_provisional_order(
                channel=SalesChannel.SHOPIFY_D2C,
                external_order_ref="SHP-10421",
                order_date=today - timedelta(days=2),
                items=[
                    {"external_product_id": "SHP-V-ROLL100", "quantity": 6, "line_gross": "4494.00"},
                    {"external_product_id": "SHP-V-MIST150", "quantity": 4, "line_gross": "2596.00"},
                ],
                gross_sales_gmv=Decimal("7090.00"),
                gst_tax_amount=Decimal("1081.53"),
                discounts_and_rebates=Decimal("350.00"),
                outbound_freight_override=Decimal("180.00"),
            )
            OmnichannelIngestionService.reconcile_settlement(
                channel=SalesChannel.SHOPIFY_D2C,
                external_order_ref="SHP-10421",
                actual_settled_payout=Decimal("6414.95"),
                settlement_utr="RZP-PAY-88412",
                payment_gateway_fees=Decimal("145.05"),
                outbound_freight_cost=Decimal("180.00"),
                actor=admin,
            )

        if not FactOrderUnitEconomics.objects.filter(external_order_ref="SHP-10489").exists():
            OmnichannelIngestionService.ingest_provisional_order(
                channel=SalesChannel.SHOPIFY_D2C,
                external_order_ref="SHP-10489",
                order_date=today,
                items=[{"external_product_id": "SHP-V-ROLL100", "quantity": 4, "line_gross": "2996.00"}],
                gross_sales_gmv=Decimal("2996.00"),
                gst_tax_amount=Decimal("457.02"),
                discounts_and_rebates=Decimal("100.00"),
            )

        # 5. Amazon Orders (1 Reconciled Hero Order + 1 Disputed Overcharge + 1 100% RTO Margin Bleeder)
        if not FactOrderUnitEconomics.objects.filter(external_order_ref="AMZ-408-9101").exists():
            OmnichannelIngestionService.ingest_provisional_order(
                channel=SalesChannel.AMAZON,
                external_order_ref="AMZ-408-9101",
                order_date=today - timedelta(days=3),
                items=[{"external_product_id": "B0D8PURA100", "quantity": 8, "line_gross": "5992.00"}],
                gross_sales_gmv=Decimal("5992.00"),
                gst_tax_amount=Decimal("914.03"),
            )
            OmnichannelIngestionService.reconcile_settlement(
                channel=SalesChannel.AMAZON,
                external_order_ref="AMZ-408-9101",
                actual_settled_payout=Decimal("4793.44"),
                settlement_utr="AMZ-NEFT-3310",
                platform_commission_fees=Decimal("1078.56"),
                outbound_freight_cost=Decimal("120.00"),
                actor=admin,
            )

        if not FactOrderUnitEconomics.objects.filter(external_order_ref="AMZ-408-RTO9").exists():
            OmnichannelIngestionService.ingest_provisional_order(
                channel=SalesChannel.AMAZON,
                external_order_ref="AMZ-408-RTO9",
                order_date=today - timedelta(days=1),
                items=[{"external_product_id": "B0D8PURA150", "quantity": 2, "line_gross": "1298.00"}],
                gross_sales_gmv=Decimal("1298.00"),
                gst_tax_amount=Decimal("198.00"),
            )
            OmnichannelIngestionService.reconcile_settlement(
                channel=SalesChannel.AMAZON,
                external_order_ref="AMZ-408-RTO9",
                actual_settled_payout=Decimal("-215.00"),
                settlement_utr="AMZ-RTO-7721",
                platform_commission_fees=Decimal("0.00"),
                outbound_freight_cost=Decimal("95.00"),
                rto_reverse_freight_cost=Decimal("120.00"),
                returns_and_rto_reversal=Decimal("1100.00"),
                is_rto=True,
                rto_inventory_returned=False,
                actor=admin,
            )

        # 6. Flipkart Order (Disputed Fee Overcharge)
        if not FactOrderUnitEconomics.objects.filter(external_order_ref="FK-OD-55821").exists():
            OmnichannelIngestionService.ingest_provisional_order(
                channel=SalesChannel.FLIPKART,
                external_order_ref="FK-OD-55821",
                order_date=today - timedelta(days=1),
                items=[{"external_product_id": "FSN-PURA-R100", "quantity": 5, "line_gross": "3745.00"}],
                gross_sales_gmv=Decimal("3745.00"),
                gst_tax_amount=Decimal("571.27"),
            )
            OmnichannelIngestionService.reconcile_settlement(
                channel=SalesChannel.FLIPKART,
                external_order_ref="FK-OD-55821",
                actual_settled_payout=Decimal("2890.00"),
                settlement_utr="FK-SETTLE-449",
                platform_commission_fees=Decimal("640.00"),
                outbound_freight_cost=Decimal("95.00"),
                extra_sla_penalty=Decimal("120.00"),
                actor=admin,
            )

        # 7. Batch Expiry Write-Off (Automated Loss)
        exp_batch = Batch.objects.filter(batch_id="BATCH-PURA-EXPIRED").first()
        if exp_batch and not BatchExpiryWriteOff.objects.filter(batch=exp_batch).exists():
            BatchExpiryWriteOff.objects.create(
                batch=exp_batch,
                writeoff_date=today - timedelta(days=2),
                units_written_off=12,
                unit_cost=rollon.base_cost,
                notes="Quarantined expired alum roll-on batch written off under FEFO audit",
                created_by=admin,
            )

        # 8. Marketing (CM3) & Fixed OPEX (EBITDA) Entries
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if not MarketingAndOpexEntry.objects.exists():
            entries = [
                (today - timedelta(days=6), today, ExpenseBucket.META_GOOGLE_ADS, SalesChannel.SHOPIFY_D2C, Decimal("4200.00"), "Meta Ads Manager", ApprovalStatus.APPROVED, True),
                (today - timedelta(days=6), today, ExpenseBucket.MARKETPLACE_ADS, SalesChannel.AMAZON, Decimal("2150.00"), "Amazon Sponsored Ads", ApprovalStatus.APPROVED, True),
                (month_start, month_end, ExpenseBucket.PAYROLL_SALARIES, None, Decimal("180000.00"), "Purastone Ops & Lab Payroll", ApprovalStatus.APPROVED, True),
                (month_start, month_end, ExpenseBucket.WAREHOUSE_OFFICE_RENT, None, Decimal("45000.00"), "Bhiwandi Fulfillment Hub Rent", ApprovalStatus.APPROVED, False),
                (today, today, ExpenseBucket.INFLUENCER_PR, SalesChannel.SHOPIFY_D2C, Decimal("3500.00"), "Skincare Creator Seeding", ApprovalStatus.PENDING, False),
            ]
            for ps, pe, bkt, ch, amt, vendor, st, paid in entries:
                MarketingAndOpexEntry.objects.create(
                    period_start_date=ps,
                    period_end_date=pe,
                    bucket=bkt,
                    target_channel=ch,
                    amount_exclusive_gst=amt,
                    gst_input_credit=(amt * Decimal("0.18")).quantize(Decimal("0.01")),
                    vendor_or_platform_name=vendor,
                    approval_status=st,
                    is_paid=paid,
                    created_by=admin,
                    approved_by=admin if st == ApprovalStatus.APPROVED else None,
                )

        # 9. Manual Offline Revenue Entries (1 Approved, 1 Pending Approval for UI review)
        if not ManualRevenueEntry.objects.filter(reference_number="POPUP-JIO-001").exists():
            m1 = ManualRevenueEntry.objects.create(
                sale_date=today - timedelta(days=1),
                reference_number="POPUP-JIO-001",
                customer_or_store_name="Jio World Drive Luxury Pop-Up",
                sku=mist,
                quantity=5,
                gross_amount=Decimal("3245.00"),
                gst_amount=Decimal("495.00"),
                discount_amount=Decimal("0.00"),
                manual_freight_and_packing=Decimal("120.00"),
                notes="Weekend wellness exhibition counter billing",
                created_by=admin,
            )
            m1.approve_and_post_to_ledger(admin_user=admin)

        if not ManualRevenueEntry.objects.filter(reference_number="CORP-GIFT-002").exists():
            ManualRevenueEntry.objects.create(
                sale_date=today,
                reference_number="CORP-GIFT-002",
                customer_or_store_name="Taj Wellness Corporate Gifting",
                sku=rollon,
                quantity=4,
                gross_amount=Decimal("2800.00"),
                gst_amount=Decimal("427.12"),
                discount_amount=Decimal("200.00"),
                manual_freight_and_packing=Decimal("90.00"),
                notes="Pending Admin Maker-Checker sign-off",
                approval_status=ApprovalStatus.PENDING,
                created_by=admin,
            )

        # 10. Complimentary Tester Burn Loss (CM3)
        if not LossAndLeakageRecord.objects.filter(category=LossCategory.TESTER_PROMO_BURN).exists():
            LossAndLeakageRecord.objects.create(
                incurred_date=today,
                category=LossCategory.TESTER_PROMO_BURN,
                channel=SalesChannel.B2B_WHOLESALE,
                units_lost=3,
                total_loss_amount=Decimal("600.00"),
                is_manual_entry=True,
                reason_notes="Spa & salon counter tester bottles dispatched",
                approval_status=ApprovalStatus.APPROVED,
                created_by=admin,
                approved_by=admin,
            )

        ensure_and_refresh_materialized_views()
        self.stdout.write(self.style.SUCCESS("Successfully seeded Purastone Phase 6 Financial Command Center data."))
