import threading
from datetime import timedelta
from decimal import Decimal
from django.test import TransactionTestCase
from django.utils import timezone
from .models import Product, InventoryLedger
from .services import InventoryEngine
from .exceptions import InsufficientStockError


class ConcurrencyLockingTests(TransactionTestCase):
    def test_concurrent_orders_prevent_overselling(self):
        today = timezone.now().date()
        product = Product.objects.create(
            sku="CONCURRENCY-SKU",
            name="Limited Edition Highlighter",
            base_price=Decimal("999.00")
        )

        # Intake exactly 10 units
        InventoryEngine.intake(
            sku=product.sku,
            quantity=10,
            batch_id="LIMITED-BATCH",
            mfg_date=today,
            expiry_date=today + timedelta(days=90),
            warehouse="WH1", aisle="A", row="1", shelf="S1"
        )

        success_count = 0
        failure_count = 0
        lock = threading.Lock()

        exceptions = []

        def try_outtake():
            nonlocal success_count, failure_count
            try:
                InventoryEngine.outtake(sku=product.sku, quantity=4)
                with lock:
                    success_count += 1
            except InsufficientStockError as e:
                with lock:
                    failure_count += 1
                    exceptions.append(('InsufficientStockError', str(e)))
            except Exception as e:
                with lock:
                    failure_count += 1
                    exceptions.append((type(e).__name__, str(e)))

        # Launch 5 concurrent threads, each wanting 4 units (total 20 units requested, 10 available)
        # Exactly 2 should succeed (4 + 4 = 8, leaving 2 remaining), and 3 must fail.
        threads = [threading.Thread(target=try_outtake) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertGreaterEqual(success_count, 1)
        self.assertLessEqual(success_count, 2)
        self.assertEqual(success_count + failure_count, 5)

        # Confirm ledger quantity did not drop below zero
        ledger = InventoryLedger.objects.get(product=product, batch_id="LIMITED-BATCH")
        self.assertGreaterEqual(ledger.quantity, 0)
