from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Product, Batch, Location, InventoryLedger, TransactionLog, WholesalerParent, WholesalerChild,
    WholesaleOrder, Invoice
)
from .services import InventoryEngine, WholesalerService
from .exceptions import (
    InsufficientStockError, InvalidAdjustmentError, ProductNotFoundError, NegativeMarginError
)
from .serializers import (
    IntakeSerializer,
    OuttakeSerializer,
    ManualAdjustmentSerializer,
    OrderPayloadSerializer,
    ProductSerializer,
    TransactionLogSerializer,
    WholesalerParentSerializer,
    WholesalerChildSerializer,
    WholesalerChildCreateSerializer,
    WholesaleOrderSerializer,
    WholesaleOrderCreateSerializer,
    WholesaleDiscountSerializer,
    InvoiceSerializer,
    BatchSerializer,
    BatchCreateSerializer,
    BatchQuarantineSerializer,
    FefoSimulationSerializer,
    DispatchGatePassSerializer
)


# ==========================================
# CORE INVENTORY VIEWS
# ==========================================

class IntakeAPIView(APIView):
    def post(self, request):
        serializer = IntakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = InventoryEngine.intake(
                sku=data['sku'],
                quantity=data['quantity'],
                batch_id=data['batch_id'],
                mfg_date=data['mfg_date'],
                expiry_date=data['expiry_date'],
                warehouse=data['warehouse'],
                aisle=data['aisle'],
                row=data['row'],
                shelf=data['shelf'],
                bin=data.get('bin'),
                user=request.user if request.user.is_authenticated else None,
                source=data.get('source', 'MANUAL')
            )
            return Response(result, status=status.HTTP_201_CREATED)
        except Product.DoesNotExist:
            return Response({"error": f"Product with SKU '{data['sku']}' does not exist."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OuttakeAPIView(APIView):
    def post(self, request):
        serializer = OuttakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = InventoryEngine.outtake(
                sku=data['sku'],
                quantity=data['quantity'],
                source=data.get('source', 'MANUAL'),
                user=request.user if request.user.is_authenticated else None
            )
            return Response(result, status=status.HTTP_200_OK)
        except (InsufficientStockError, ProductNotFoundError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ManualAdjustmentAPIView(APIView):
    def post(self, request):
        serializer = ManualAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = InventoryEngine.adjust(
                sku=data['sku'],
                batch_id=data['batch_id'],
                location_id=str(data['location_id']),
                quantity_change=data['quantity_change'],
                reason_code=data['reason_code'],
                user=request.user if request.user.is_authenticated else None
            )
            return Response(result, status=status.HTTP_200_OK)
        except (InvalidAdjustmentError, InsufficientStockError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OrderProcessingAPIView(APIView):
    def post(self, request):
        serializer = OrderPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = InventoryEngine.process_order(
                order_id=data['order_id'],
                source=data['source'],
                items=data['items'],
                user=request.user if request.user.is_authenticated else None
            )
            return Response(result, status=status.HTTP_200_OK)
        except (InsufficientStockError, ProductNotFoundError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventorySummaryAPIView(APIView):
    def get(self, request, sku=None):
        if sku:
            try:
                summary = InventoryEngine.get_inventory_summary(sku)
                return Response(summary, status=status.HTTP_200_OK)
            except Product.DoesNotExist:
                return Response({"error": f"Product with SKU '{sku}' not found."}, status=status.HTTP_404_NOT_FOUND)

        products = Product.objects.all().order_by('sku')
        summaries = [InventoryEngine.get_inventory_summary(p.sku) for p in products]
        return Response(summaries, status=status.HTTP_200_OK)


class TransactionLogListView(APIView):
    def get(self, request):
        logs = TransactionLog.objects.select_related('product', 'batch', 'user').order_by('-timestamp')[:100]
        serializer = TransactionLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==========================================
# WHOLESALER MODULE VIEWS
# ==========================================

class WholesalerParentListCreateAPIView(APIView):
    def get(self, request):
        parents = WholesalerParent.objects.prefetch_related('branches').all().order_by('-created_at')
        serializer = WholesalerParentSerializer(parents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        name = request.data.get('name')
        gstin = request.data.get('gstin')
        master_email = request.data.get('master_email')

        if not name or not gstin or not master_email:
            return Response({"error": "name, gstin, and master_email are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parent = WholesalerService.onboard_parent(name=name, gstin=gstin, master_email=master_email)
            serializer = WholesalerParentSerializer(parent)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WholesalerApproveAPIView(APIView):
    def post(self, request, parent_id):
        try:
            parent = WholesalerService.approve_parent(parent_id)
            serializer = WholesalerParentSerializer(parent)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except WholesalerParent.DoesNotExist:
            return Response({"error": "Wholesaler parent not found."}, status=status.HTTP_404_NOT_FOUND)


class WholesalerChildListCreateAPIView(APIView):
    def get(self, request):
        parent_id = request.query_params.get('parent_id')
        queryset = WholesalerChild.objects.select_related('parent', 'user').all().order_by('branch_name')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        serializer = WholesalerChildSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = WholesalerChildCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        try:
            child = WholesalerService.create_child_account(
                parent_id=d['parent_id'],
                branch_name=d['branch_name'],
                store_id=d['store_id'],
                shipping_address=d['shipping_address'],
                contact_person=d['contact_person'],
                username=d['username'],
                password=d.get('password')
            )
            return Response(WholesalerChildSerializer(child).data, status=status.HTTP_201_CREATED)
        except (ValueError, WholesalerParent.DoesNotExist) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WholesaleOrderListCreateAPIView(APIView):
    def get(self, request):
        parent_id = request.query_params.get('parent_id')
        child_id = request.query_params.get('child_id')
        queryset = WholesaleOrder.objects.select_related(
            'parent_wholesaler', 'child_wholesaler', 'invoice'
        ).prefetch_related('items__product').all().order_by('-created_at')

        if parent_id:
            queryset = queryset.filter(parent_wholesaler_id=parent_id)
        if child_id:
            queryset = queryset.filter(child_wholesaler_id=child_id)

        serializer = WholesaleOrderSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = WholesaleOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        try:
            order = WholesalerService.create_draft_order(
                child_id=d['child_id'],
                items=d['items'],
                po_number=d.get('po_number'),
                notes=d.get('notes')
            )
            return Response(WholesaleOrderSerializer(order).data, status=status.HTTP_201_CREATED)
        except (ValueError, WholesalerChild.DoesNotExist, Product.DoesNotExist) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WholesaleOrderDetailAPIView(APIView):
    def get(self, request, order_id):
        try:
            order = WholesaleOrder.objects.select_related(
                'parent_wholesaler', 'child_wholesaler', 'invoice'
            ).prefetch_related('items__product').get(id=order_id)
            return Response(WholesaleOrderSerializer(order).data, status=status.HTTP_200_OK)
        except WholesaleOrder.DoesNotExist:
            return Response({"error": "Wholesale order not found."}, status=status.HTTP_404_NOT_FOUND)


class WholesaleOrderApplyDiscountAPIView(APIView):
    def post(self, request, order_id):
        serializer = WholesaleDiscountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        try:
            order = WholesalerService.apply_discount(
                order_id=order_id,
                discount_type=d['discount_type'],
                discount_value=d['discount_value']
            )
            return Response(WholesaleOrderSerializer(order).data, status=status.HTTP_200_OK)
        except (NegativeMarginError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except WholesaleOrder.DoesNotExist:
            return Response({"error": "Wholesale order not found."}, status=status.HTTP_404_NOT_FOUND)


class WholesaleOrderConfirmAPIView(APIView):
    def post(self, request, order_id):
        try:
            result = WholesalerService.confirm_order(
                order_id=order_id,
                user=request.user if request.user.is_authenticated else None
            )
            return Response(result, status=status.HTTP_200_OK)
        except InsufficientStockError as e:
            return Response({"error": f"FEFO Stock Deduction Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, WholesaleOrder.DoesNotExist) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WholesaleAnalyticsAPIView(APIView):
    def get(self, request, parent_id=None):
        try:
            analytics = WholesalerService.get_analytics(parent_id=parent_id)
            return Response(analytics, status=status.HTTP_200_OK)
        except WholesalerParent.DoesNotExist:
            return Response({"error": "Wholesaler parent not found."}, status=status.HTTP_404_NOT_FOUND)


class InvoiceListAPIView(APIView):
    def get(self, request):
        invoices = Invoice.objects.select_related('order__parent_wholesaler', 'order__child_wholesaler').order_by('-created_at')[:100]
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==========================================
# PHASE 2: MINERAL SKINCARE PRODUCT & BATCH TRACEABILITY
# ==========================================

class ProductListCreateAPIView(APIView):
    """
    Mineral Skincare SKU Directory:
    Supports filtering by category, skincare_line, mineral_actives, HSN, and barcode.
    """
    def get(self, request):
        qs = Product.objects.all().order_by('sku')
        category = request.query_params.get('category')
        line = request.query_params.get('skincare_line')
        active = request.query_params.get('mineral_active')
        hsn = request.query_params.get('hsn_code')
        search = request.query_params.get('search')

        if category:
            qs = qs.filter(category=category)
        if line:
            qs = qs.filter(skincare_line=line)
        if active:
            qs = qs.filter(mineral_actives__icontains=active)
        if hsn:
            qs = qs.filter(hsn_code=hsn)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(sku__icontains=search)

        serializer = ProductSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailAPIView(APIView):
    """
    Product SKU retrieval and update.
    """
    def get(self, request, sku):
        try:
            product = Product.objects.get(sku=sku)
            return Response(ProductSerializer(product).data, status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            return Response({"error": f"Product '{sku}' not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, sku):
        try:
            product = Product.objects.get(sku=sku)
            serializer = ProductSerializer(product, data=request.data, partial=False)
            serializer.is_valid(raise_exception=True)
            updated = serializer.save()
            return Response(ProductSerializer(updated).data, status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            return Response({"error": f"Product '{sku}' not found."}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, sku):
        try:
            product = Product.objects.get(sku=sku)
            serializer = ProductSerializer(product, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            updated = serializer.save()
            return Response(ProductSerializer(updated).data, status=status.HTTP_200_OK)
        except Product.DoesNotExist:
            return Response({"error": f"Product '{sku}' not found."}, status=status.HTTP_404_NOT_FOUND)


class BatchListCreateAPIView(APIView):
    """
    Formulation Batch Directory & Compliance Tracker.
    Filter by product_sku, quarantine_status, near_expiry, expired.
    """
    def get(self, request):
        qs = Batch.objects.select_related('product').all().order_by('expiry_date', 'mfg_date')
        product_sku = request.query_params.get('product_sku')
        quarantined = request.query_params.get('quarantined')
        near_expiry = request.query_params.get('near_expiry')

        if product_sku:
            qs = qs.filter(product_id=product_sku)
        if quarantined is not None:
            is_q = quarantined.lower() in ('1', 'true', 'yes')
            qs = qs.filter(quarantine_status=is_q)
        if near_expiry:
            from datetime import date, timedelta
            today = date.today()
            qs = qs.filter(expiry_date__gt=today, expiry_date__lte=today + timedelta(days=90))

        serializer = BatchSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = BatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = serializer.save()
        return Response(BatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class BatchDetailAPIView(APIView):
    """
    Detailed Batch Genealogy & Traceability.
    """
    def get(self, request, batch_id):
        try:
            report = InventoryEngine.get_batch_traceability(batch_id=batch_id)
            return Response(report, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


class BatchQuarantineAPIView(APIView):
    """
    Toggle quarantine status for a formulation lot.
    """
    def post(self, request, batch_id):
        serializer = BatchQuarantineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = InventoryEngine.set_batch_quarantine(
                batch_id=batch_id,
                quarantine=serializer.validated_data['quarantine'],
                reason=serializer.validated_data['reason'],
                user=request.user if request.user.is_authenticated else None
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


class FefoPreviewAPIView(APIView):
    """
    Pre-dispatch FEFO lot allocation simulation.
    """
    def post(self, request):
        serializer = FefoSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = InventoryEngine.simulate_fefo_pick(
                sku=serializer.validated_data['sku'],
                quantity=serializer.validated_data['quantity']
            )
            return Response(preview, status=status.HTTP_200_OK)
        except (ValueError, ProductNotFoundError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DispatchGatePassOuttakeAPIView(APIView):
    """
    Atomically depletes FEFO stock tied to gate-pass issuance and LR generation.
    """
    def post(self, request):
        serializer = DispatchGatePassSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            manifest = InventoryEngine.dispatch_gate_pass_fefo_outtake(
                dispatch_reference=data['dispatch_reference'],
                items=data['items'],
                user=request.user if request.user.is_authenticated else None,
                gate_pass_number=data.get('gate_pass_number'),
                lr_number=data.get('lr_number')
            )
            return Response(manifest, status=status.HTTP_200_OK)
        except (InsufficientStockError, ProductNotFoundError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
