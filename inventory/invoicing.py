import os
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Purastone Brand Colors
BURNT_CLAY = colors.HexColor('#A05A3A')
BURNT_CLAY_DARK = colors.HexColor('#7A3E24')
SOFT_LINEN = colors.HexColor('#F5E9DD')
SOFT_LINEN_LIGHT = colors.HexColor('#FBF7F2')
EARTH_CHARCOAL = colors.HexColor('#23160E')
MUTED_TEXT = colors.HexColor('#6E5849')


def generate_invoice_pdf(order) -> str:
    """
    Generates a PDF invoice for a confirmed WholesaleOrder and returns the media URL.
    """
    invoices_dir = Path(settings.MEDIA_ROOT) / 'invoices'
    invoices_dir.mkdir(parents=True, exist_ok=True)
    filename = f"invoice_{order.id}.pdf"
    file_path = invoices_dir / filename

    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=BURNT_CLAY,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'InvoiceSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=MUTED_TEXT,
        spaceAfter=14
    )

    body_style = ParagraphStyle(
        'InvoiceBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=EARTH_CHARCOAL,
        leading=13
    )

    bold_body = ParagraphStyle(
        'InvoiceBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    elements = []

    # 1. Header Banner
    elements.append(Paragraph("PURASTONE &bull; B2B WHOLESALE TAX INVOICE", title_style))
    elements.append(Paragraph(
        "Purastone Natural Care & Mineral Logistics Pvt. Ltd. | GSTIN: 27AABCP1092F1Z8 | Central WH Hub",
        subtitle_style
    ))
    elements.append(Spacer(1, 0.1 * inch))

    # 2. Wholesaler & Order Metadata Grid
    parent = order.parent_wholesaler
    child = order.child_wholesaler
    
    po_text = f"<br/>PO Ref: <b>{order.po_number}</b>" if getattr(order, 'po_number', None) else ""
    meta_data = [
        [
            Paragraph("<b>BILLED TO (PARENT LEGAL ENTITY):</b>", bold_body),
            Paragraph("<b>SHIP TO (BRANCH / STORE):</b>", bold_body),
            Paragraph("<b>INVOICE METADATA:</b>", bold_body),
        ],
        [
            Paragraph(f"<b>{parent.name}</b><br/>GSTIN: {parent.gstin}<br/>Master Email: {parent.master_email}", body_style),
            Paragraph(f"<b>{child.branch_name}</b> (Store: {child.store_id})<br/>Contact: {child.contact_person}<br/>Address: {child.shipping_address}", body_style),
            Paragraph(f"Invoice Ref: <b>{str(order.id)[:8]}...</b>{po_text}<br/>Status: <b>{order.status}</b><br/>Date: {order.created_at.strftime('%d-%b-%Y')}", body_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[2.3 * inch, 2.7 * inch, 2.3 * inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT_LINEN_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, SOFT_LINEN),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.2 * inch))

    # 3. Line Items Table
    table_data = [
        [
            Paragraph("<b>SKU</b>", bold_body),
            Paragraph("<b>ITEM DESCRIPTION</b>", bold_body),
            Paragraph("<b>QTY</b>", bold_body),
            Paragraph("<b>UNIT PRICE</b>", bold_body),
            Paragraph("<b>GST %</b>", bold_body),
            Paragraph("<b>GST AMT</b>", bold_body),
            Paragraph("<b>LINE TOTAL</b>", bold_body)
        ]
    ]

    for item in order.items.select_related('product').all():
        gst_pct = getattr(item, 'gst_percentage', Decimal('18.00'))
        gst_amt = getattr(item, 'gst_amount', Decimal('0.00'))
        line_tot = getattr(item, 'line_total', None)
        if not line_tot or line_tot == 0:
            line_tot = (item.quantity * item.locked_b2b_price) + gst_amt

        table_data.append([
            Paragraph(item.product.sku, body_style),
            Paragraph(item.product.name, body_style),
            Paragraph(str(item.quantity), body_style),
            Paragraph(f"INR {item.locked_b2b_price:.2f}", body_style),
            Paragraph(f"{gst_pct:.1f}%", body_style),
            Paragraph(f"INR {gst_amt:.2f}", body_style),
            Paragraph(f"INR {line_tot:.2f}", bold_body),
        ])

    items_table = Table(table_data, colWidths=[1.4 * inch, 2.2 * inch, 0.5 * inch, 1.0 * inch, 0.6 * inch, 0.8 * inch, 1.0 * inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BURNT_CLAY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, SOFT_LINEN),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SOFT_LINEN_LIGHT]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.15 * inch))

    # 4. Summary & Discount Breakdown Table
    grand_total_val = getattr(order, 'grand_total', None)
    if not grand_total_val or grand_total_val == 0:
        grand_total_val = order.final_value + getattr(order, 'total_gst', Decimal('0.00'))

    summary_data = [
        [Paragraph("Taxable Subtotal:", body_style), Paragraph(f"INR {order.subtotal:.2f}", body_style)],
        [Paragraph("<b>Custom Approved Discount:</b>", body_style), Paragraph(f"<b>- INR {order.discount_amount:.2f}</b>", bold_body)],
        [Paragraph("Net Taxable Value:", body_style), Paragraph(f"INR {order.final_value:.2f}", body_style)],
        [Paragraph("Total GST:", body_style), Paragraph(f"INR {getattr(order, 'total_gst', Decimal('0.00')):.2f}", body_style)],
        [Paragraph("<b>GRAND TOTAL PAYABLE:</b>", bold_body), Paragraph(f"<b>INR {grand_total_val:.2f}</b>", bold_body)],
    ]
    summary_table = Table(summary_data, colWidths=[2.2 * inch, 1.5 * inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 4), (-1, 4), SOFT_LINEN),
        ('BOX', (0, 0), (-1, -1), 1, SOFT_LINEN),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))

    # Right align the summary table
    right_aligned = Table([[Spacer(1, 1), summary_table]], colWidths=[3.8 * inch, 3.7 * inch])
    right_aligned.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(right_aligned)

    elements.append(Spacer(1, 0.3 * inch))
    footer_text = Paragraph(
        "<i>Thank you for partnering with PURASTONE. Ancient Purity Meets Modern Care.<br/>"
        "Stock allocated strictly via FEFO outtake protocols. All disputes subject to jurisdiction.</i>",
        subtitle_style
    )
    elements.append(footer_text)

    doc.build(elements)

    media_url = f"{settings.MEDIA_URL}invoices/{filename}"
    return media_url

