from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Product, BundleMapping, InventoryLedger, TransactionLog


class InventoryAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='api_operator', password='password123')
        self.client.force_authenticate(user=self.user)
        self.today = timezone.now().date()

        self.product = Product.objects.create(
            sku="SERUM-VIT-C",
            name="Vitamin C Glow Serum",
            base_price=Decimal("699.00")
        )

        self.bundle = BundleMapping.objects.create(
            promo_sku="BOGO-VIT-C",
            base_product=self.product,
            quantity_multiplier=2
        )

    def test_api_intake_and_summary(self):
        payload = {
            "sku": self.product.sku,
            "quantity": 100,
            "batch_id": "BATCH-API-01",
            "mfg_date": str(self.today),
            "expiry_date": str(self.today + timedelta(days=365)),
            "warehouse": "CENTRAL",
            "aisle": "A1",
            "row": "R1",
            "shelf": "S1",
            "bin": "B1"
        }
        res = self.client.post(reverse('api_intake'), payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["quantity_added"], 100)

        # Query summary
        summary_res = self.client.get(reverse('api_inventory_detail', kwargs={'sku': self.product.sku}))
        self.assertEqual(summary_res.status_code, status.HTTP_200_OK)
        self.assertEqual(summary_res.data["total_quantity"], 100)
        self.assertEqual(summary_res.data["sellable_quantity"], 100)
        self.assertEqual(summary_res.data["expired_quantity"], 0)

    def test_api_bogo_order_processing(self):
        # Intake 20 base serums
        self.client.post(reverse('api_intake'), {
            "sku": self.product.sku,
            "quantity": 20,
            "batch_id": "BATCH-API-02",
            "mfg_date": str(self.today),
            "expiry_date": str(self.today + timedelta(days=200)),
            "warehouse": "CENTRAL",
            "aisle": "A1",
            "row": "R1",
            "shelf": "S2",
            "bin": "B1"
        }, format='json')

        # Order 3 BOGO units -> should deduct 6 base serums
        order_payload = {
            "order_id": "ORD-AMZ-555",
            "source": "AMAZON",
            "items": [
                {"sku": "BOGO-VIT-C", "quantity": 3}
            ]
        }
        order_res = self.client.post(reverse('api_order'), order_payload, format='json')
        self.assertEqual(order_res.status_code, status.HTTP_200_OK)
        item = order_res.data["fulfilled_items"][0]
        self.assertEqual(item["actual_quantity_deducted"], 6)
        self.assertEqual(item["pick_directions"][0]["shelf"], "S2")

        # Verify ledger has 14
        ledger = InventoryLedger.objects.get(batch_id="BATCH-API-02")
        self.assertEqual(ledger.quantity, 14)

    def test_api_manual_adjustment_validation(self):
        intake_res = self.client.post(reverse('api_intake'), {
            "sku": self.product.sku,
            "quantity": 30,
            "batch_id": "BATCH-API-03",
            "mfg_date": str(self.today),
            "expiry_date": str(self.today + timedelta(days=150)),
            "warehouse": "CENTRAL",
            "aisle": "A1",
            "row": "R1",
            "shelf": "S3"
        }, format='json')
        loc_id = intake_res.data["location_id"]

        # Missing reason code
        bad_adj = self.client.post(reverse('api_adjust'), {
            "sku": self.product.sku,
            "batch_id": "BATCH-API-03",
            "location_id": loc_id,
            "quantity_change": -5,
            "reason_code": ""
        }, format='json')
        self.assertEqual(bad_adj.status_code, status.HTTP_400_BAD_REQUEST)

        # Successful manual adjustment with reason code
        good_adj = self.client.post(reverse('api_adjust'), {
            "sku": self.product.sku,
            "batch_id": "BATCH-API-03",
            "location_id": loc_id,
            "quantity_change": -3,
            "reason_code": "INFLUENCER_GIFT"
        }, format='json')
        self.assertEqual(good_adj.status_code, status.HTTP_200_OK)
        self.assertEqual(good_adj.data["new_balance"], 27)

