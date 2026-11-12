from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.exceptions import InsufficientStockError, ProductNotFoundError
from .exports import build_boardroom_pdf_pack, build_ca_csv_export, build_ca_xlsx_export
from .materialized import ensure_and_refresh_materialized_views
from .models import (
    _q2,
    ApprovalStatus,
    ChannelSkuMapping,
    FactOrderUnitEconomics,
    FinancialAuditLog,
    FinancialTreasuryConfig,
    LorryReceipt,
    LossAndLeakageRecord,
    ManualRevenueEntry,
    MarketingAndOpexEntry,
    SalesChannel,
)
from .serializers import (
    ChannelSkuMappingSerializer,
    FactOrderUnitEconomicsSerializer,
    FinancialAuditLogSerializer,
    FinancialTreasuryConfigSerializer,
    LorryReceiptSerializer,
    LossAndLeakageRecordSerializer,
    ManualRevenueEntrySerializer,
    MarketingAndOpexEntrySerializer,
)
from .services import (
    MakerCheckerService,
    OmnichannelIngestionService,
    WaterfallAnalyticsService,
    resolve_date_range,
)
from .tasks import refresh_financial_materialized_views_task, sync_marketplace_settlement_task


def _get_dates(request):
    return resolve_date_range(
        preset=request.query_params.get("preset", "MTD"),
        start_str=request.query_params.get("start_date"),
        end_str=request.query_params.get("end_date"),
    )


def _actor(request):
    return request.user if getattr(request, "user", None) and request.user.is_authenticated else None


class CommandCenterSummaryAPIView(APIView):
    def get(self, request):
        start, end, p_start, p_end = _get_dates(request)
        data = WaterfallAnalyticsService.get_command_center_summary(start, end, p_start, p_end)
        return Response(data, status=status.HTTP_200_OK)


class UnitEconomicsExplorerAPIView(APIView):
    def get(self, request):
        start, end, _, _ = _get_dates(request)
        return Response(
            WaterfallAnalyticsService.get_unit_economics_explorer(start, end),
            status=status.HTTP_200_OK,
        )


class SettlementReconcilerAPIView(APIView):
    def get(self, request):
        start, end, _, _ = _get_dates(request)
        channel = request.query_params.get("channel")
        status_filter = request.query_params.get("status")
        return Response(
            WaterfallAnalyticsService.get_settlement_reconciler(start, end, channel=channel, status_filter=status_filter),
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        """Triggers reconciliation of a marketplace order settlement against UTR & actual fees."""
        try:
            d = request.data
            econ = OmnichannelIngestionService.reconcile_settlement(
                channel=d["channel"],
                external_order_ref=d["external_order_ref"],
                actual_settled_payout=Decimal(str(d["actual_settled_payout"])),
                settlement_utr=d["settlement_utr"],
                platform_commission_fees=(
                    Decimal(str(d["platform_commission_fees"])) if d.get("platform_commission_fees") is not None else None
                ),
                payment_gateway_fees=(
                    Decimal(str(d["payment_gateway_fees"])) if d.get("payment_gateway_fees") is not None else None
                ),
                outbound_freight_cost=(
                    Decimal(str(d["outbound_freight_cost"])) if d.get("outbound_freight_cost") is not None else None
                ),
                rto_reverse_freight_cost=(
                    Decimal(str(d["rto_reverse_freight_cost"])) if d.get("rto_reverse_freight_cost") is not None else None
                ),
                returns_and_rto_reversal=(
                    Decimal(str(d["returns_and_rto_reversal"])) if d.get("returns_and_rto_reversal") is not None else None
                ),
                is_rto=bool(d.get("is_rto", False)),
                rto_inventory_returned=bool(d.get("rto_inventory_returned", True)),
                extra_sla_penalty=Decimal(str(d.get("extra_sla_penalty", "0.00"))),
                actor=_actor(request),
            )
            ensure_and_refresh_materialized_views()
            return Response(FactOrderUnitEconomicsSerializer(econ).data, status=status.HTTP_200_OK)
        except FactOrderUnitEconomics.DoesNotExist:
            return Response({"error": "Order economics record not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LossesIntelligenceAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        start, end, _, _ = _get_dates(request)
        intel = WaterfallAnalyticsService.get_losses_intelligence(start, end)
        pending = LossAndLeakageRecord.objects.filter(approval_status=ApprovalStatus.PENDING).order_by("-created_at")
        intel["pending_approvals"] = LossAndLeakageRecordSerializer(pending, many=True).data
        return Response(intel, status=status.HTTP_200_OK)

    def post(self, request):
        """Logs a manual loss/write-off into the Maker-Checker approval queue."""
        serializer = LossAndLeakageRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = serializer.save(
            is_manual_entry=True,
            approval_status=ApprovalStatus.PENDING,
            created_by=_actor(request),
        )
        FinancialAuditLog.record(
            actor=_actor(request),
            action="CREATE",
            entity_type="LossAndLeakageRecord",
            entity_id=str(record.id),
            snapshot={"category": record.category, "amount": str(record.total_loss_amount)},
            notes="Logged manual loss entry (PENDING_APPROVAL)",
        )
        return Response(LossAndLeakageRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class ManualRevenueListCreateAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        entries = ManualRevenueEntry.objects.select_related("sku").order_by("-sale_date", "-created_at")[:100]
        return Response(ManualRevenueEntrySerializer(entries, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ManualRevenueEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(approval_status=ApprovalStatus.PENDING, created_by=_actor(request))
        FinancialAuditLog.record(
            actor=_actor(request),
            action="CREATE",
            entity_type="ManualRevenueEntry",
            entity_id=str(entry.id),
            snapshot={"reference_number": entry.reference_number, "gross_amount": str(entry.gross_amount)},
            notes="Logged manual offline sale (PENDING_APPROVAL)",
        )
        return Response(ManualRevenueEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class MarketingOpexListCreateAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        entries = MarketingAndOpexEntry.objects.order_by("-period_start_date", "-created_at")[:150]
        return Response(MarketingAndOpexEntrySerializer(entries, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = MarketingAndOpexEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(approval_status=ApprovalStatus.PENDING, created_by=_actor(request))
        FinancialAuditLog.record(
            actor=_actor(request),
            action="CREATE",
            entity_type="MarketingAndOpexEntry",
            entity_id=str(entry.id),
            snapshot={"bucket": entry.bucket, "amount": str(entry.amount_exclusive_gst)},
            notes="Logged marketing/OPEX entry (PENDING_APPROVAL)",
        )
        return Response(MarketingAndOpexEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class BulkCsvImportAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        import_type = (request.data.get("type") or "opex").lower()
        csv_text = request.data.get("csv_content", "")
        if not csv_text and "file" in request.FILES:
            csv_text = request.FILES["file"].read().decode("utf-8")

        if not csv_text or not str(csv_text).strip():
            return Response({"error": "Provide 'csv_content' or upload a CSV 'file'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if import_type == "sales":
                rows = MakerCheckerService.import_manual_sales_csv(csv_text, created_by=_actor(request))
            else:
                rows = MakerCheckerService.import_opex_csv(csv_text, created_by=_actor(request))
            return Response({"status": "IMPORTED_PENDING_APPROVAL", "count": len(rows)}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": f"CSV Parse Error: {e}"}, status=status.HTTP_400_BAD_REQUEST)


class MakerCheckerDecisionAPIView(APIView):
    """
    Admin / Proprietor-only approval endpoint transitioning PENDING entries to APPROVED/REJECTED
    and writing immutable AuditLog snapshots.
    """

    @transaction.atomic
    def post(self, request, entity_type, entry_id):
        if not MakerCheckerService.is_admin_request(request):
            return Response(
                {"error": "RBAC Denied: Only Admin / Proprietor can approve or reject manual financial entries."},
                status=status.HTTP_403_FORBIDDEN,
            )

        decision = (request.data.get("action") or "APPROVE").upper()
        if decision not in ("APPROVE", "REJECT"):
            return Response({"error": "action must be 'APPROVE' or 'REJECT'."}, status=status.HTTP_400_BAD_REQUEST)

        admin_user = _actor(request)
        etype = entity_type.lower()

        try:
            if etype == "manual-sale":
                obj = ManualRevenueEntry.objects.select_for_update().get(pk=entry_id)
                if decision == "APPROVE":
                    econ = obj.approve_and_post_to_ledger(admin_user=admin_user)
                    ensure_and_refresh_materialized_views()
                    return Response(
                        {"status": "APPROVED", "posted_order_econ_id": str(econ.id), "cm2": str(econ.cm2_amount)},
                        status=status.HTTP_200_OK,
                    )
                obj.approval_status = ApprovalStatus.REJECTED
                obj.approved_by = admin_user
                obj.save(update_fields=["approval_status", "approved_by"])
                FinancialAuditLog.record(admin_user, "REJECT", "ManualRevenueEntry", str(obj.id), {"reference_number": obj.reference_number})
                return Response({"status": "REJECTED"}, status=status.HTTP_200_OK)

            elif etype == "opex":
                obj = MarketingAndOpexEntry.objects.select_for_update().get(pk=entry_id)
                obj.approval_status = ApprovalStatus.APPROVED if decision == "APPROVE" else ApprovalStatus.REJECTED
                obj.approved_by = admin_user
                obj.save(update_fields=["approval_status", "approved_by"])
                FinancialAuditLog.record(
                    admin_user,
                    decision,
                    "MarketingAndOpexEntry",
                    str(obj.id),
                    {"bucket": obj.bucket, "amount": str(obj.amount_exclusive_gst)},
                )
                ensure_and_refresh_materialized_views()
                return Response({"status": obj.approval_status}, status=status.HTTP_200_OK)

            elif etype == "loss":
                obj = LossAndLeakageRecord.objects.select_for_update().get(pk=entry_id)
                obj.approval_status = ApprovalStatus.APPROVED if decision == "APPROVE" else ApprovalStatus.REJECTED
                obj.approved_by = admin_user
                obj.save(update_fields=["approval_status", "approved_by"])
                FinancialAuditLog.record(
                    admin_user,
                    decision,
                    "LossAndLeakageRecord",
                    str(obj.id),
                    {"category": obj.category, "amount": str(obj.total_loss_amount)},
                )
                ensure_and_refresh_materialized_views()
                return Response({"status": obj.approval_status}, status=status.HTTP_200_OK)

            return Response({"error": f"Unknown entity_type '{entity_type}'."}, status=status.HTTP_400_BAD_REQUEST)
        except (ManualRevenueEntry.DoesNotExist, MarketingAndOpexEntry.DoesNotExist, LossAndLeakageRecord.DoesNotExist):
            return Response({"error": "Entry not found."}, status=status.HTTP_404_NOT_FOUND)
        except (InsufficientStockError, ProductNotFoundError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FinancialAuditLogListAPIView(APIView):
    def get(self, request):
        logs = FinancialAuditLog.objects.select_related("actor").all()[:100]
        return Response(FinancialAuditLogSerializer(logs, many=True).data, status=status.HTTP_200_OK)


class WorkingCapitalRunwayAPIView(APIView):
    def get(self, request):
        start, end, _, _ = _get_dates(request)
        return Response(
            WaterfallAnalyticsService.get_working_capital_and_runway(start, end),
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        """Updates Cash in Bank / Interest / Tax config OR marks a B2B AR / LR AP settled."""
        action = request.data.get("action", "UPDATE_TREASURY")
        if action == "COLLECT_B2B_AR":
            econ = FactOrderUnitEconomics.objects.get(external_order_ref=request.data["order_ref"], channel=SalesChannel.B2B_WHOLESALE)
            amt = _q2(Decimal(str(request.data["amount"])))
            econ.amount_collected = _q2(econ.amount_collected + amt)
            econ.save()
            ensure_and_refresh_materialized_views()
            return Response({"status": "AR_COLLECTED", "amount_collected": str(econ.amount_collected)}, status=status.HTTP_200_OK)

        treasury, _ = FinancialTreasuryConfig.objects.get_or_create(pk=1)
        serializer = FinancialTreasuryConfigSerializer(treasury, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChannelSkuMappingListCreateAPIView(APIView):
    def get(self, request):
        qs = ChannelSkuMapping.objects.select_related("internal_sku").all()
        return Response(ChannelSkuMappingSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ChannelSkuMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LorryReceiptListCreateAPIView(APIView):
    def get(self, request):
        lrs = LorryReceipt.objects.select_related("wholesale_order").all()[:100]
        return Response(LorryReceiptSerializer(lrs, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = LorryReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lr = serializer.save()
        return Response(LorryReceiptSerializer(lr).data, status=status.HTTP_201_CREATED)


class LorryReceiptVerifyPodAPIView(APIView):
    def post(self, request, lr_id):
        try:
            lr = LorryReceipt.objects.get(pk=lr_id)
            lr.pod_status = request.data.get("pod_status", "CLEAN")
            lr.pod_damage_units = int(request.data.get("pod_damage_units", 0))
            lr.pod_damage_cost = _q2(Decimal(str(request.data.get("pod_damage_cost", "0.00"))))
            lr.pod_notes = request.data.get("pod_notes", lr.pod_notes)
            lr.pod_verified_at = timezone.now()
            if request.data.get("mark_ap_paid"):
                lr.transporter_payable_status = "PAID"
            lr.save()
            return Response(LorryReceiptSerializer(lr).data, status=status.HTTP_200_OK)
        except LorryReceipt.DoesNotExist:
            return Response({"error": "LorryReceipt not found."}, status=status.HTTP_404_NOT_FOUND)


class MarketplaceWebhookAPIView(APIView):
    """Ingests Shopify GraphQL + Razorpay, Amazon SP-API, and Flipkart Settlement payloads via Celery."""

    def post(self, request, channel):
        ch_map = {
            "shopify": SalesChannel.SHOPIFY_D2C,
            "shopify_d2c": SalesChannel.SHOPIFY_D2C,
            "amazon": SalesChannel.AMAZON,
            "flipkart": SalesChannel.FLIPKART,
        }
        norm_ch = ch_map.get(channel.lower())
        if not norm_ch:
            return Response({"error": f"Unsupported channel '{channel}'."}, status=status.HTTP_400_BAD_REQUEST)

        task_res = sync_marketplace_settlement_task.delay(channel=norm_ch, payload=request.data)
        return Response({"status": "ACCEPTED", "channel": norm_ch, "task_id": str(task_res.id)}, status=status.HTTP_202_ACCEPTED)


class RefreshMaterializedViewsAPIView(APIView):
    def post(self, request):
        task_res = refresh_financial_materialized_views_task.delay()
        return Response({"status": "REFRESHED", "task_id": str(task_res.id), "result": task_res.result}, status=status.HTTP_200_OK)


class ExportBoardroomPdfAPIView(APIView):
    def get(self, request):
        start, end, _, _ = _get_dates(request)
        pdf_bytes = build_boardroom_pdf_pack(start, end)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="PURASTONE_Boardroom_PnL_{start}_{end}.pdf"'
        return resp


class ExportCaExcelAPIView(APIView):
    def get(self, request):
        start, end, _, _ = _get_dates(request)
        xlsx_bytes = build_ca_xlsx_export(start, end)
        resp = HttpResponse(
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="PURASTONE_CA_Ledger_{start}_{end}.xlsx"'
        return resp


class ExportCaCsvAPIView(APIView):
    def get(self, request):
        start, end, _, _ = _get_dates(request)
        csv_text = build_ca_csv_export(start, end)
        resp = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="PURASTONE_CA_Ledger_{start}_{end}.csv"'
        return resp

