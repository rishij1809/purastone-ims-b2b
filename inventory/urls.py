from django.urls import path
from .views import (
    IntakeAPIView,
    OuttakeAPIView,
    ManualAdjustmentAPIView,
    OrderProcessingAPIView,
    InventorySummaryAPIView,
    TransactionLogListView,
    WholesalerParentListCreateAPIView,
    WholesalerApproveAPIView,
    WholesalerChildListCreateAPIView,
    WholesaleOrderListCreateAPIView,
    WholesaleOrderDetailAPIView,
    WholesaleOrderApplyDiscountAPIView,
    WholesaleOrderConfirmAPIView,
    WholesaleAnalyticsAPIView,
    InvoiceListAPIView
)

urlpatterns = [
    # Core Inventory Endpoints
    path('intake/', IntakeAPIView.as_view(), name='api_intake'),
    path('outtake/', OuttakeAPIView.as_view(), name='api_outtake'),
    path('adjust/', ManualAdjustmentAPIView.as_view(), name='api_adjust'),
    path('order/', OrderProcessingAPIView.as_view(), name='api_order'),
    path('inventory/', InventorySummaryAPIView.as_view(), name='api_inventory_list'),
    path('inventory/<str:sku>/', InventorySummaryAPIView.as_view(), name='api_inventory_detail'),
    path('transactions/', TransactionLogListView.as_view(), name='api_transactions'),

    # B2B Wholesaler Module Endpoints
    path('wholesale/parents/', WholesalerParentListCreateAPIView.as_view(), name='api_wholesale_parents'),
    path('wholesale/parents/<int:parent_id>/approve/', WholesalerApproveAPIView.as_view(), name='api_wholesale_approve'),
    path('wholesale/children/', WholesalerChildListCreateAPIView.as_view(), name='api_wholesale_children'),
    path('wholesale/orders/', WholesaleOrderListCreateAPIView.as_view(), name='api_wholesale_orders'),
    path('wholesale/orders/<uuid:order_id>/', WholesaleOrderDetailAPIView.as_view(), name='api_wholesale_order_detail'),
    path('wholesale/orders/<uuid:order_id>/discount/', WholesaleOrderApplyDiscountAPIView.as_view(), name='api_wholesale_order_discount'),
    path('wholesale/orders/<uuid:order_id>/confirm/', WholesaleOrderConfirmAPIView.as_view(), name='api_wholesale_order_confirm'),
    path('wholesale/analytics/', WholesaleAnalyticsAPIView.as_view(), name='api_wholesale_analytics_master'),
    path('wholesale/analytics/<int:parent_id>/', WholesaleAnalyticsAPIView.as_view(), name='api_wholesale_analytics_individual'),
    path('wholesale/invoices/', InvoiceListAPIView.as_view(), name='api_wholesale_invoices'),
]
