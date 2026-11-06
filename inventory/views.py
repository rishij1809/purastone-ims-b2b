from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    Product, TransactionLog, WholesalerParent, WholesalerChild,
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
    InvoiceSerializer
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
