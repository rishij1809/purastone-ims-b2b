import csv
import io
import zipfile
from xml.sax.saxutils import escape
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .models import FactOrderUnitEconomics, LossAndLeakageRecord, MarketingAndOpexEntry
from .services import WaterfallAnalyticsService

BURNT_CLAY = colors.HexColor("#a05a3a")
SOFT_LINEN = colors.HexColor("#f5e9dd")
ESPRESSO = colors.HexColor("#23160e")
LIGHT_CREAM = colors.HexColor("#fbf7f2")


def build_boardroom_pdf_pack(start_date: date, end_date: date) -> bytes:
    """Generates a Boardroom-ready Purastone 6-Tier P&L, Omnichannel & Runway PDF Pack."""
    summary = WaterfallAnalyticsService.get_command_center_summary(start_date, end_date)
    losses = WaterfallAnalyticsService.get_losses_intelligence(start_date, end_date)
    wc = WaterfallAnalyticsService.get_working_capital_and_runway(start_date, end_date)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PuraTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=BURNT_CLAY, alignment=0, spaceAfter=4)
    sub_style = ParagraphStyle("PuraSub", parent=styles["Normal"], fontSize=9, textColor=ESPRESSO, spaceAfter=10)
    h2_style = ParagraphStyle("PuraH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=BURNT_CLAY, spaceBefore=10, spaceAfter=6)

    elems = []
    elems.append(Paragraph("PURASTONE NATURAL CARE — BOARDROOM P&L PACK", title_style))
    elems.append(Paragraph(f"Executive Financial Command Center | Period: {start_date.isoformat()} to {end_date.isoformat()} | Currency: INR", sub_style))

    # 1. 6-Tier Waterfall Table
    elems.append(Paragraph("1. Six-Tier Financial Waterfall (CM1 -> CM2 -> CM3 -> EBITDA -> PAT)", h2_style))
    wf_data = [["Waterfall Tier / Line Item", "Amount (INR)"]]
    for step in summary["waterfall_bridge"]:
        wf_data.append([step["step"], f"{step['amount']:,.2f}"])

    wf_table = Table(wf_data, colWidths=[125 * mm, 50 * mm])
    wf_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BURNT_CLAY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8c7b5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_CREAM]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), SOFT_LINEN),
    ]))
    elems.append(wf_table)
    elems.append(Spacer(1, 6 * mm))

    # 2. Omnichannel Comparison Matrix
    elems.append(Paragraph("2. Omnichannel Margin Comparison", h2_style))
    ch_data = [["Channel", "Orders", "Net Rev", "CM1 %", "CM2 %", "CM3 (INR)", "CM3 %"]]
    for ch in summary["omnichannel_matrix"]:
        ch_data.append([
            ch["channel"],
            str(ch["orders"]),
            ch["net_revenue"],
            f"{ch['cm1_pct']}%",
            f"{ch['cm2_pct']}%",
            ch["cm3"],
            f"{ch['cm3_pct']}%",
        ])
    ch_table = Table(ch_data, colWidths=[45 * mm, 16 * mm, 28 * mm, 18 * mm, 18 * mm, 30 * mm, 20 * mm])
    ch_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ESPRESSO),
        ("TEXTCOLOR", (0, 0), (-1, 0), SOFT_LINEN),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8c7b5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_CREAM]),
    ]))
    elems.append(ch_table)
    elems.append(Spacer(1, 6 * mm))

    # 3. Losses & Working Capital Summary
    elems.append(Paragraph("3. Loss Intelligence & Treasury Runway Snapshot", h2_style))
    kpis = summary["kpis"]
    meta_rows = [
        ["Total Approved Losses & Leakage", f"INR {losses['total_losses']}"],
        ["FEFO Expiry & QC Write-Offs", f"INR {losses['pillars']['fefo_expiry_and_qc']}"],
        ["LR Transit & RTO Breakage", f"INR {losses['pillars']['transit_and_rto_breakage']}"],
        ["Cash in Bank Balance", f"INR {wc['treasury']['cash_in_bank_balance']}"],
        ["Uncollected B2B AR / Locked Inventory COGS", f"INR {wc['accrual_vs_cash_bridge']['uncollected_b2b_ar']} / INR {wc['inventory_capital']['total_locked_cogs']}"],
        ["Burn Status / Runway Months", f"{wc['runway']['burn_status']} ({wc['runway']['runway_months']} mo)"],
        ["Net Profit Margin %", f"{kpis['net_profit_pct']}% (Net Cash Flow: INR {kpis['net_cash_flow']})"],
    ]
    meta_table = Table(meta_rows, colWidths=[95 * mm, 80 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8c7b5")),
        ("BACKGROUND", (0, 0), (0, -1), SOFT_LINEN),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    elems.append(meta_table)

    doc.build(elems)
    return buf.getvalue()


def build_ca_csv_export(start_date: date, end_date: date) -> str:
    """Generates a CA-ready UTF-8 CSV ledger of Order Unit Economics."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Order Date", "Channel", "Order Ref", "Status", "GMV", "GST", "Discounts",
        "Returns/RTO", "Net Revenue", "Batch COGS", "Packaging", "Inward Freight",
        "CM1", "Platform Fees", "Gateway Fees", "Outbound Freight", "RTO Freight",
        "Pick-Pack", "Breakage", "CM2", "UTR", "Expected Payout", "Actual Payout", "Discrepancy"
    ])
    for o in FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date)).order_by("order_date"):
        writer.writerow([
            o.order_date.isoformat(), o.channel, o.external_order_ref, o.reconciliation_status,
            o.gross_sales_gmv, o.gst_tax_amount, o.discounts_and_rebates, o.returns_and_rto_reversal,
            o.net_revenue, o.batch_formulation_cogs, o.primary_packaging_cost, o.inward_freight_overhead,
            o.cm1_amount, o.platform_commission_fees, o.payment_gateway_fees, o.outbound_freight_cost,
            o.rto_reverse_freight_cost, o.master_carton_and_pick_pack, o.transit_breakage_cost,
            o.cm2_amount, o.settlement_utr, o.expected_payout_amount, o.actual_settled_payout, o.discrepancy_amount,
        ])
    return buf.getvalue()


def _col_letter(idx: int) -> str:
    s = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def _sheet_xml(rows: list[list]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r_idx, row in enumerate(rows, start=1):
        lines.append(f'<row r="{r_idx}">')
        for c_idx, val in enumerate(row, start=1):
            ref = f"{_col_letter(c_idx)}{r_idx}"
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                lines.append(f'<c r="{ref}" t="n"><v>{val}</v></c>')
            else:
                txt = escape("" if val is None else str(val))
                lines.append(f'<c r="{ref}" t="inlineStr"><is><t>{txt}</t></is></c>')
        lines.append('</row>')
    lines.append('</sheetData></worksheet>')
    return "".join(lines)


def build_ca_xlsx_export(start_date: date, end_date: date) -> bytes:
    """Builds a valid multi-sheet CA-Ready .xlsx workbook with zero native C dependencies."""
    summary = WaterfallAnalyticsService.get_command_center_summary(start_date, end_date)
    pnl_rows = [["Waterfall Step", "Amount (INR)", "Type"]] + [
        [s["step"], s["amount"], s["type"]] for s in summary["waterfall_bridge"]
    ]

    order_rows = [[
        "Order Date", "Channel", "External Ref", "Reconciliation Status", "GMV", "GST",
        "Discounts", "RTO Reversal", "Net Revenue", "Batch COGS", "CM1", "CM2", "Expected Payout", "Actual Payout", "UTR"
    ]]
    for o in FactOrderUnitEconomics.objects.filter(order_date__range=(start_date, end_date)).order_by("order_date"):
        order_rows.append([
            o.order_date.isoformat(), o.channel, o.external_order_ref, o.reconciliation_status,
            float(o.gross_sales_gmv), float(o.gst_tax_amount), float(o.discounts_and_rebates),
            float(o.returns_and_rto_reversal), float(o.net_revenue), float(o.batch_formulation_cogs),
            float(o.cm1_amount), float(o.cm2_amount), float(o.expected_payout_amount),
            float(o.actual_settled_payout), o.settlement_utr,
        ])

    opex_rows = [["Period Start", "Period End", "Bucket", "Channel", "Vendor", "Amount Excl GST", "GST Credit", "Status"]]
    for e in MarketingAndOpexEntry.objects.filter(period_start_date__lte=end_date, period_end_date__gte=start_date):
        opex_rows.append([
            e.period_start_date.isoformat(), e.period_end_date.isoformat(), e.bucket,
            e.target_channel or "SHARED", e.vendor_or_platform_name, float(e.amount_exclusive_gst),
            float(e.gst_input_credit), e.approval_status,
        ])

    loss_rows = [["Date", "Category", "Channel", "Units Lost", "Loss Amount", "Manual?", "Status", "Notes"]]
    for l in LossAndLeakageRecord.objects.filter(incurred_date__range=(start_date, end_date)):
        loss_rows.append([
            l.incurred_date.isoformat(), l.category, l.channel, l.units_lost,
            float(l.total_loss_amount), str(l.is_manual_entry), l.approval_status, l.reason_notes,
        ])

    sheets = [
        ("PnL_Waterfall", pnl_rows),
        ("Order_Unit_Economics", order_rows),
        ("Marketing_And_OPEX", opex_rows),
        ("Loss_Register", loss_rows),
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        content_types = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        ]
        wb_sheets = []
        wb_rels = []
        for idx, (name, rows) in enumerate(sheets, start=1):
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            wb_sheets.append(f'<sheet name="{escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
            wb_rels.append(
                f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>'
            )
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(rows))

        content_types.append("</Types>")
        zf.writestr("[Content_Types].xml", "".join(content_types))
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(wb_sheets)}</sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(wb_rels)}</Relationships>',
        )

    return buf.getvalue()

