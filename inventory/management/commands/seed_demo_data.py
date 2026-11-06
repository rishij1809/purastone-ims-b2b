from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from inventory.models import Product, BundleMapping, WholesalerParent, WholesalerChild
from inventory.services import InventoryEngine, WholesalerService


class Command(BaseCommand):
    help = 'Seeds initial test products, bundles, batches, locations, and wholesaler accounts.'

    def handle(self, *args, **options):
        today = timezone.now().date()

        # 1. Purastone Flagship Mineral Roll-On with COGS and B2B Price
        rollon, _ = Product.objects.get_or_create(
            sku="PURA-ALUM-ROLLON-100",
            defaults={
                "name": "Purastone Natural Alum After-Shave Roll-On 100ml",
                "base_price": Decimal("749.00"),
                "base_cost": Decimal("250.00"),
                "default_b2b_price": Decimal("450.00")
            }
        )
        rollon.base_cost = Decimal("250.00")
        rollon.default_b2b_price = Decimal("450.00")
        rollon.save()

        # 2. Purastone BOGO Bundle Mapping
        BundleMapping.objects.get_or_create(
            promo_sku="PROMO-BOGO-PURASTONE",
            defaults={"base_product": rollon, "quantity_multiplier": 2}
        )

        # 3. Purastone Mineral Facial Mist with COGS and B2B Price
        mist, _ = Product.objects.get_or_create(
            sku="PURA-MINERAL-MIST-150",
            defaults={
                "name": "Purastone Soothing Mineral Facial Mist 150ml",
                "base_price": Decimal("649.00"),
                "base_cost": Decimal("200.00"),
                "default_b2b_price": Decimal("380.00")
            }
        )
        mist.base_cost = Decimal("200.00")
        mist.default_b2b_price = Decimal("380.00")
        mist.save()

        # 4. Ruby Matte Lipstick
        product, _ = Product.objects.get_or_create(
            sku="LIPSTICK-RUBY-01",
            defaults={
                "name": "Ruby Matte Liquid Lipstick",
                "base_price": Decimal("599.00"),
                "base_cost": Decimal("180.00"),
                "default_b2b_price": Decimal("350.00")
            }
        )
        product.base_cost = Decimal("180.00")
        product.default_b2b_price = Decimal("350.00")
        product.save()

        BundleMapping.objects.get_or_create(
            promo_sku="PROMO-BOGO-LIPSTICK",
            defaults={"base_product": product, "quantity_multiplier": 2}
        )

        # Intake Batches for PURASTONE Roll-On
        InventoryEngine.intake(
            sku=rollon.sku,
            quantity=30,
            batch_id="BATCH-PURA-26A",
            mfg_date=today - timedelta(days=60),
            expiry_date=today + timedelta(days=20),
            warehouse="CENTRAL_WH", aisle="A1", row="R1", shelf="S01", bin="B01"
        )
        InventoryEngine.intake(
            sku=rollon.sku,
            quantity=120,
            batch_id="BATCH-PURA-26B",
            mfg_date=today - timedelta(days=10),
            expiry_date=today + timedelta(days=180),
            warehouse="CENTRAL_WH", aisle="A1", row="R1", shelf="S02", bin="B02"
        )
        InventoryEngine.intake(
            sku=rollon.sku,
            quantity=12,
            batch_id="BATCH-PURA-EXPIRED",
            mfg_date=today - timedelta(days=220),
            expiry_date=today - timedelta(days=15),
            warehouse="CENTRAL_WH", aisle="A1", row="R9", shelf="S99", bin="EXP"
        )

        # Stock for Purastone Mist
        InventoryEngine.intake(
            sku=mist.sku,
            quantity=75,
            batch_id="BATCH-MIST-01",
            mfg_date=today - timedelta(days=20),
            expiry_date=today + timedelta(days=210),
            warehouse="CENTRAL_WH", aisle="A2", row="R1", shelf="S03", bin="B01"
        )

        # 5. Wholesaler Parents
        aura, _ = WholesalerParent.objects.get_or_create(
            gstin="27AABCA1234F1Z5",
            defaults={
                "name": "Aura Wellness Retail Pvt Ltd",
                "master_email": "procurement@aurawellness.com",
                "status": "APPROVED"
            }
        )
        zenith, _ = WholesalerParent.objects.get_or_create(
            gstin="29XYZPA9999K1Z2",
            defaults={
                "name": "Zenith Spas & Salons",
                "master_email": "accounts@zenithspas.com",
                "status": "PENDING"
            }
        )

        # 6. Child Branches under Aura
        if not WholesalerChild.objects.filter(store_id="AURA-MUM-01").exists():
            child1 = WholesalerService.create_child_account(
                parent_id=aura.id,
                branch_name="Bandra Flagship",
                store_id="AURA-MUM-01",
                shipping_address="Linking Rd, Bandra West, Mumbai, MH - 400050",
                contact_person="Rajesh Sharma",
                username="aura_bandra"
            )
            # Create a sample confirmed order for demonstration with PDF invoice
            order = WholesalerService.create_draft_order(
                child_id=child1.id,
                items=[{"sku": rollon.sku, "quantity": 10}]
            )
            WholesalerService.apply_discount(order_id=str(order.id), discount_type="FLAT", discount_value=300.00)
            WholesalerService.confirm_order(order_id=str(order.id))

        if not WholesalerChild.objects.filter(store_id="AURA-BLR-01").exists():
            WholesalerService.create_child_account(
                parent_id=aura.id,
                branch_name="Indiranagar Branch",
                store_id="AURA-BLR-01",
                shipping_address="100ft Rd, Indiranagar, Bangalore, KA - 560038",
                contact_person="Kavita Rao",
                username="aura_indiranagar"
            )

        self.stdout.write(self.style.SUCCESS('Successfully seeded Purastone inventory & B2B Wholesaler accounts.'))
