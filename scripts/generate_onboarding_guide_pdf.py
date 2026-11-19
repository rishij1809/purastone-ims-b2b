import os
import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and print total page numbers and running headers/footers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Header (Pages 2+)
        if self._pageNumber > 1:
            self.drawString(36, A4[1] - 25, "PURA STONE ENTERPRISE ERP — REAL DATA & SYSTEM INTEGRATION SPECIFICATION")
            self.drawRightString(A4[0] - 36, A4[1] - 25, "CONFIDENTIAL & PROPRIETARY")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(36, A4[1] - 28, A4[0] - 36, A4[1] - 28)

        # Footer (All pages)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 32, A4[0] - 36, 32)
        self.drawString(36, 20, "Pura Stone Mineral Skincare — Executive Implementation & Data Onboarding Guide")
        self.drawRightString(A4[0] - 36, 20, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def build_pdf(filename="PURA_STONE_DATA_ONBOARDING_AND_INTEGRATION_GUIDE.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'SectionHeading1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f766e"), # Pura Stone Teal
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1e293b")
    )

    bold_body_style = ParagraphStyle(
        'BoldBodyDark',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#0f172a")
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1e293b")
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f172a")
    )

    table_cell_code = ParagraphStyle(
        'TableCellCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#0f766e")
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0369a1")
    )

    story = []

    # Title Banner
    story.append(Paragraph("PURA STONE ENTERPRISE ERP & FINANCIAL COMMAND CENTER", title_style))
    story.append(Paragraph("<b>MASTER DATA ONBOARDING, API CREDENTIALS & INTEGRATION REQUIREMENTS SPECIFICATION</b><br/>"
                           "<i>A comprehensive operational guide listing all API keys, master catalog tables, carrier rate cards, batch records, and financial baselines needed to connect real-world data to the live system.</i>", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f766e"), spaceAfter=10))

    # Executive Summary Box
    summary_html = (
        "<b>EXECUTIVE PURPOSE & DATA PIPELINE ARCHITECTURE:</b><br/>"
        "The Pura Stone ERP operates a unified 6-tier unit-economics and financial waterfall engine: "
        "<b>GMV → Net Revenue → CM1 → CM2 → CM3 → EBITDA & Net Profit</b>. To transition from the current "
        "synthetic demo environment to full production, the platform requires exact operational inputs across <b>8 core domains</b>: "
        "(1) Omnichannel & Payment Gateway APIs, (2) Logistics & Government E-Way Bill APIs, (3) Digital Ad Platform APIs, "
        "(4) Master Product & Omnichannel SKU Mapping, (5) Warehouse & FEFO Formulation Batch Inventory, "
        "(6) B2B Wholesaler & Stockist Directory, (7) Fixed OPEX & Unit Formulation Costings, and (8) Cloud Server Environment Keys. "
        "Each section below specifies the exact parameter names, source portals, and the precise business calculation it powers."
    )
    summary_table = Table([[Paragraph(summary_html, callout_style)]], colWidths=[523])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#99f6e4")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # SECTION 1: Omnichannel & Payment Gateway API Credentials
    story.append(Paragraph("1. Omnichannel Marketplace & Payment Gateway API Credentials", h1_style))
    story.append(Paragraph("These credentials connect automated ingestion pipelines that ingest real customer orders, fees, refunds, and bank payouts.", body_style))
    story.append(Spacer(1, 4))

    headers1 = [
        Paragraph("Integration Domain", table_header_style),
        Paragraph("Exact Keys / Parameters Needed", table_header_style),
        Paragraph("Where to Obtain", table_header_style),
        Paragraph("Operational Purpose & Business Impact", table_header_style),
    ]

    rows1 = [
        [
            Paragraph("<b>Shopify D2C Store</b>", table_cell_bold),
            Paragraph("• Store Domain (e.g. <code>purastone.myshopify.com</code>)<br/>"
                      "• Admin API Access Token (<code>shpat_...</code>)<br/>"
                      "• API Secret Key<br/>"
                      "• Webhook Signing Secret", table_cell_style),
            Paragraph("Shopify Admin → Apps → Develop Apps → Create an App → Admin API Scopes (read_orders, read_products, read_inventory)", table_cell_style),
            Paragraph("<b>Real-time D2C Sales Ingestion:</b> Automatically captures customer orders, promo discounts, customer addresses, taxes, and triggers FEFO stock allocation upon checkout.", table_cell_style)
        ],
        [
            Paragraph("<b>Amazon India (SP-API)</b>", table_cell_bold),
            Paragraph("• LWA Client ID & Secret<br/>"
                      "• SP-API Refresh Token<br/>"
                      "• AWS IAM Role ARN & Access Key/Secret<br/>"
                      "• Seller Merchant ID (e.g. <code>A21TJ...</code>)<br/>"
                      "• Marketplace ID (<code>A21TJRUUN4KGV</code> for IN)", table_cell_style),
            Paragraph("Amazon Seller Central → Partner Network → Developer Central → Register App (Orders API, Finances API, Reports API)", table_cell_style),
            Paragraph("<b>FBA / FBM Order & Fee Reconciliation:</b> Extracts gross GMV, referral fees, closing fees, weight-handling shipping fees, and settlement UTR files to compute true CM2.", table_cell_style)
        ],
        [
            Paragraph("<b>Flipkart Seller Platform</b>", table_cell_bold),
            Paragraph("• Flipkart App ID / Client ID<br/>"
                      "• App Secret Key<br/>"
                      "• Flipkart Seller ID<br/>"
                      "• Settlement API Bearer Token", table_cell_style),
            Paragraph("Flipkart Seller Hub → Developer Console → Self-Serve API Integration (Orders & Post-Order Services)", table_cell_style),
            Paragraph("<b>Marketplace Net Realization:</b> Ingests marketplace commission deductions, collection charges, pick-pack fees, and customer returns/RTO penalty deductions.", table_cell_style)
        ],
        [
            Paragraph("<b>Razorpay Payment Gateway</b>", table_cell_bold),
            Paragraph("• Key ID (<code>rzp_live_...</code>)<br/>"
                      "• Key Secret<br/>"
                      "• Webhook Secret", table_cell_style),
            Paragraph("Razorpay Dashboard → Settings → API Keys & Webhooks (Enable: order.paid, refund.processed, payment.captured)", table_cell_style),
            Paragraph("<b>Transaction Fee & Payout Auditing:</b> Verifies exact MDR fee (typically 1.8%–2.2% + 18% GST), tracks payment failures, customer chargebacks, and automated bank settlement reconciliation.", table_cell_style)
        ],
        [
            Paragraph("<b>Stripe Gateway (International)</b>", table_cell_bold),
            Paragraph("• Publishable Key (<code>pk_live_...</code>)<br/>"
                      "• Secret Key (<code>sk_live_...</code>)<br/>"
                      "• Webhook Signing Secret (<code>whsec_...</code>)", table_cell_style),
            Paragraph("Stripe Dashboard → Developers → API Keys & Webhooks", table_cell_style),
            Paragraph("<b>Global Cross-Border D2C:</b> Ingests international multi-currency transactions (USD, EUR, GBP), FX conversion losses, and international gateway fees.", table_cell_style)
        ]
    ]

    t1 = Table([headers1] + rows1, colWidths=[85, 140, 140, 158])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t1)
    story.append(Spacer(1, 10))

    # SECTION 2: Logistics, TMS & Statutory Government APIs
    story.append(Paragraph("2. Logistics Carriers, Transport Management (TMS) & Statutory Portals", h1_style))
    story.append(Paragraph("Enables automated dispatch, multi-carrier label generation, B2B Lorry Receipt (LR) tracking, and E-Way Bill generation.", body_style))
    story.append(Spacer(1, 4))

    headers2 = [
        Paragraph("Platform / System", table_header_style),
        Paragraph("Required Keys & Inputs", table_header_style),
        Paragraph("Where to Obtain", table_header_style),
        Paragraph("Operational Purpose & Business Impact", table_header_style),
    ]

    rows2 = [
        [
            Paragraph("<b>D2C Aggregator (Shiprocket / Pickrr)</b>", table_cell_bold),
            Paragraph("• API User Email & Password<br/>"
                      "• Bearer Token (JWT)<br/>"
                      "• Webhook Authentication Token", table_cell_style),
            Paragraph("Shiprocket Panel → Settings → API → Configure & Generate Keys", table_cell_style),
            Paragraph("<b>D2C Shipping & RTO Cost Allocation:</b> Auto-assigns forward courier, tracks AWB numbers, monitors transit damage, and allocates reverse shipping charges on RTO orders directly to order CM2.", table_cell_style)
        ],
        [
            Paragraph("<b>Surface Couriers (Delhivery / Bluedart)</b>", table_cell_bold),
            Paragraph("• Production API Token<br/>"
                      "• Client Account Name / Master Pin<br/>"
                      "• Pickup Location Name", table_cell_style),
            Paragraph("Delhivery One Portal / Bluedart Enterprise Integration Account", table_cell_style),
            Paragraph("<b>Heavy Cargo & Volumetric Freight:</b> Handles multi-carton surface dispatches with volumetric weight calculations and proof-of-delivery (POD) sync.", table_cell_style)
        ],
        [
            Paragraph("<b>B2B Transporters (VRL / TCI / Rivigo Rate Cards)</b>", table_cell_bold),
            Paragraph("• Transporter Master Contract Rates (per kg / per carton rate matrix)<br/>"
                      "• Transporter GSTIN & Transporter ID<br/>"
                      "• Contract Minimum Freight Charges & Surcharges (FOV, Hamali, Bilty)", table_cell_style),
            Paragraph("Existing physical freight agreements & rate-card annexures with transport partners", table_cell_style),
            Paragraph("<b>B2B Lorry Receipt (LR) Cost Engine:</b> Dynamically calculates prepaid vs to-pay freight slabs, loading charges, and transit breakage liability for wholesale dispatches.", table_cell_style)
        ],
        [
            Paragraph("<b>E-Way Bill & E-Invoice Portal (NIC / GSP)</b>", table_cell_bold),
            Paragraph("• GSP Client ID & Client Secret (ClearTax, Masters India, or NIC)<br/>"
                      "• E-Way Bill Portal Username & Password<br/>"
                      "• E-Invoice Portal API Credentials", table_cell_style),
            Paragraph("ewaybillgst.gov.in & einvoice1.gst.gov.in → API Registration → GSP Selection", table_cell_style),
            Paragraph("<b>Statutory GST Compliance:</b> Automatically generates 12-digit E-Way Bill numbers and IRN QR codes on B2B invoices exceeding ₹50,000 threshold prior to vehicle dispatch.", table_cell_style)
        ]
    ]

    t2 = Table([headers2] + rows2, colWidths=[85, 140, 140, 158])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 10))

    # SECTION 3: Advertising Networks for CM3 & ROAS
    story.append(Paragraph("3. Digital Advertising Platforms (Automated CM3 & Blended CAC)", h1_style))
    story.append(Paragraph("Automates daily marketing spend synchronization to compute accurate Contribution Margin 3 (CM3) without manual spreadsheets.", body_style))
    story.append(Spacer(1, 4))

    headers3 = [
        Paragraph("Ad Platform", table_header_style),
        Paragraph("Required Keys & Identifiers", table_header_style),
        Paragraph("Where to Obtain", table_header_style),
        Paragraph("Operational Purpose & Business Impact", table_header_style),
    ]

    rows3 = [
        [
            Paragraph("<b>Meta Ads (Facebook & Instagram)</b>", table_cell_bold),
            Paragraph("• System User Access Token (Never-expiring)<br/>"
                      "• Meta Ad Account ID (<code>act_...</code>)<br/>"
                      "• Meta Pixel ID & Conversion API Key", table_cell_style),
            Paragraph("business.facebook.com → Business Settings → System Users → Generate Token (ads_read, ads_management)", table_cell_style),
            Paragraph("<b>D2C Customer Acquisition Cost (CAC):</b> Syncs daily D2C ad spend per skincare line (Serum, Cleanser, Alum) to deduce CM3 and Blended ROAS.", table_cell_style)
        ],
        [
            Paragraph("<b>Google Ads (Search, Shopping & PMax)</b>", table_cell_bold),
            Paragraph("• Developer Token<br/>"
                      "• OAuth2 Client ID & Client Secret<br/>"
                      "• Refresh Token<br/>"
                      "• Google Ads Customer ID (<code>xxx-xxx-xxxx</code>)", table_cell_style),
            Paragraph("Google Cloud Console (Project APIs) & Google Ads Manager Account (MCC) → Tools → API Center", table_cell_style),
            Paragraph("<b>Search Intent & Conversion Attribution:</b> Tracks Google Shopping & Performance Max ad spend against high-intent mineral skincare search queries.", table_cell_style)
        ],
        [
            Paragraph("<b>Amazon / Flipkart Sponsored Ads</b>", table_cell_bold),
            Paragraph("• Amazon Advertising API Profile ID & Token<br/>"
                      "• Flipkart PLA / PCA Ad Account ID", table_cell_style),
            Paragraph("advertising.amazon.in & Flipkart Advertising Panel", table_cell_style),
            Paragraph("<b>Marketplace Advertising (ACOS/TACOS):</b> Allocates marketplace sponsored product ad costs directly to Amazon/Flipkart CM3 calculations.", table_cell_style)
        ]
    ]

    t3 = Table([headers3] + rows3, colWidths=[85, 140, 140, 158])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t3)
    story.append(PageBreak())

    # SECTION 4: Master Skincare Catalog & Omnichannel SKU Directory
    story.append(Paragraph("4. Master Mineral Skincare Catalog & SKU Mapping Directory (Excel / CSV)", h1_style))
    story.append(Paragraph("The central master directory of all Pura Stone formulations, barcodes, physical dimensions, and wholesale pricing structures.", body_style))
    story.append(Spacer(1, 4))

    headers4 = [
        Paragraph("Field Name", table_header_style),
        Paragraph("Data Type / Format", table_header_style),
        Paragraph("Example Value", table_header_style),
        Paragraph("Why Required & How the ERP Uses It", table_header_style),
    ]

    rows4 = [
        [
            Paragraph("<b>sku</b>", table_cell_code),
            Paragraph("String (Unique ID)", table_cell_style),
            Paragraph("<code>PURA-SERUM-50ML</code>", table_cell_code),
            Paragraph("Primary identifier for all inventory transactions, batch allocations, and invoice lines.", table_cell_style)
        ],
        [
            Paragraph("<b>name</b>", table_cell_code),
            Paragraph("String (Max 255)", table_cell_style),
            Paragraph("Mineral Glow Facial Serum 50ml", table_cell_style),
            Paragraph("Commercial display name printed on GST invoices, packing lists, and carton labels.", table_cell_style)
        ],
        [
            Paragraph("<b>category</b>", table_cell_code),
            Paragraph("Enum Choice", table_cell_style),
            Paragraph("<code>SERUM</code>, <code>CLAY_MASK</code>, <code>MINERAL_CLEANSER</code>", table_cell_code),
            Paragraph("Categorizes product lines for analytics, inventory valuation, and category margin analysis.", table_cell_style)
        ],
        [
            Paragraph("<b>skincare_line</b>", table_cell_code),
            Paragraph("Enum Choice", table_cell_style),
            Paragraph("<code>MINERAL_GLOW</code>, <code>PURA_ALUM_WELLNESS</code>", table_cell_code),
            Paragraph("Groups formulations into brand lines for marketing attribution and CEO reporting.", table_cell_style)
        ],
        [
            Paragraph("<b>mineral_actives</b>", table_cell_code),
            Paragraph("String", table_cell_style),
            Paragraph("Potassium Alum, Kaolin Clay, Zinc Oxide", table_cell_style),
            Paragraph("Product specifications displayed in B2B catalog and wholesale portal.", table_cell_style)
        ],
        [
            Paragraph("<b>packaging_format</b>", table_cell_code),
            Paragraph("String", table_cell_style),
            Paragraph("50ml Glass Dropper Bottle with Mono-Carton", table_cell_style),
            Paragraph("Packaging specifications used by warehouse staff for packing verification.", table_cell_style)
        ],
        [
            Paragraph("<b>barcode_ean13_upc</b>", table_cell_code),
            Paragraph("13-digit Barcode", table_cell_style),
            Paragraph("<code>8901234567890</code>", table_cell_code),
            Paragraph("Scanned by warehouse barcode scanners during intake, pick/pack, and dispatch audits.", table_cell_style)
        ],
        [
            Paragraph("<b>hsn_code</b>", table_cell_code),
            Paragraph("8-digit Code", table_cell_style),
            Paragraph("<code>33049990</code> (Skincare)", table_cell_code),
            Paragraph("Mandatory statutory HSN code required on GST tax invoices and E-Way bills (18% GST).", table_cell_style)
        ],
        [
            Paragraph("<b>dead_weight_kg</b>", table_cell_code),
            Paragraph("Decimal (3 places)", table_cell_style),
            Paragraph("<code>0.180</code> (180 grams)", table_cell_code),
            Paragraph("Physical gross scale weight used by TMS to calculate courier freight slabs.", table_cell_style)
        ],
        [
            Paragraph("<b>length_cm, width_cm, height_cm</b>", table_cell_code),
            Paragraph("Decimal (cm)", table_cell_style),
            Paragraph("<code>4.5 x 4.5 x 12.0</code>", table_cell_code),
            Paragraph("Computes volumetric weight <code>(L*W*H)/5000</code> to prevent courier freight billing penalties.", table_cell_style)
        ],
        [
            Paragraph("<b>inner_pack_count</b>", table_cell_code),
            Paragraph("Integer", table_cell_style),
            Paragraph("<code>6</code> units", table_cell_code),
            Paragraph("Inner shrink-wrap pack size for wholesale handling.", table_cell_style)
        ],
        [
            Paragraph("<b>master_carton_qty</b>", table_cell_code),
            Paragraph("Integer", table_cell_style),
            Paragraph("<code>24</code> units", table_cell_code),
            Paragraph("Master shipping carton capacity. Governs volume slab discounts and freight containerization.", table_cell_style)
        ],
        [
            Paragraph("<b>base_price (MRP)</b>", table_cell_code),
            Paragraph("Decimal (₹)", table_cell_style),
            Paragraph("<code>1200.00</code>", table_cell_code),
            Paragraph("Maximum Retail Price printed on packaging. Base anchor for PTR/PTS discount calculations.", table_cell_style)
        ],
        [
            Paragraph("<b>default_b2b_price (PTR)</b>", table_cell_code),
            Paragraph("Decimal (₹)", table_cell_style),
            Paragraph("<code>900.00</code> (25% off MRP)", table_cell_code),
            Paragraph("Standard wholesale baseline Price-to-Retailer before volume slab discounts.", table_cell_style)
        ],
        [
            Paragraph("<b>base_cost (COGS)</b>", table_cell_code),
            Paragraph("Decimal (₹)", table_cell_style),
            Paragraph("<code>300.00</code>", table_cell_code),
            Paragraph("Total landed formulation + primary packaging cost. Strictly protects negative margin floor.", table_cell_style)
        ],
        [
            Paragraph("<b>Shopify / Amazon / Flipkart Mapping</b>", table_cell_code),
            Paragraph("External IDs", table_cell_style),
            Paragraph("Variant: <code>4589211</code><br/>ASIN: <code>B09XYZ...</code><br/>FSN: <code>SKCFA...</code>", table_cell_code),
            Paragraph("Omnichannel SKU cross-referencing table so external marketplace orders decrement correct inventory.", table_cell_style)
        ]
    ]

    t4 = Table([headers4] + rows4, colWidths=[90, 80, 115, 238])
    t4.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t4)
    story.append(Spacer(1, 10))

    # SECTION 5: Physical Warehouse Locations & Live Batch Traceability
    story.append(Paragraph("5. Physical Warehouse Locations & FEFO Formulation Batch Registry", h1_style))
    story.append(Paragraph("Powers the First-Expired, First-Out (FEFO) warehouse picking engine, near-expiry alerts, and batch quarantine controls.", body_style))
    story.append(Spacer(1, 4))

    headers5 = [
        Paragraph("Data Element", table_header_style),
        Paragraph("Required Inputs", table_header_style),
        Paragraph("Format / Standard", table_header_style),
        Paragraph("Operational Purpose & Business Impact", table_header_style),
    ]

    rows5 = [
        [
            Paragraph("<b>Warehouse Topology</b>", table_cell_bold),
            Paragraph("• Warehouse Name/Code<br/>"
                      "• Aisle Identifier (e.g. A1, A2)<br/>"
                      "• Rack / Row Number (e.g. R01)<br/>"
                      "• Shelf Level (e.g. S01, S02)<br/>"
                      "• Bin Code (optional)", table_cell_style),
            Paragraph("Physical warehouse layout mapping (CSV or Excel)", table_cell_style),
            Paragraph("<b>Exact Bin Routing:</b> Generates precise warehouse pick-paths for dispatch staff to eliminate stock misplacement and speed up order fulfillment.", table_cell_style)
        ],
        [
            Paragraph("<b>Live Formulation Batches</b>", table_cell_bold),
            Paragraph("• Batch / Lot Number (e.g. <code>BATCH-2026-ALUM-01</code>)<br/>"
                      "• SKU Code<br/>"
                      "• Manufacturing Date (<code>mfg_date</code>)<br/>"
                      "• Expiry Date (<code>expiry_date</code>)<br/>"
                      "• Formulated Shelf Life (e.g. 730 days / 24 months)", table_cell_style),
            Paragraph("Production Batch Logs from manufacturing unit / contract manufacturer", table_cell_style),
            Paragraph("<b>Strict FEFO Allocation:</b> Guarantees older batches nearing expiry are dispatched first. Automatically flags near-expiry batches (≤ 90 days) and locks expired stock.", table_cell_style)
        ],
        [
            Paragraph("<b>Compliance & Quality Control (COA)</b>", table_cell_bold),
            Paragraph("• Certificate of Analysis (COA) PDF files<br/>"
                      "• Microbial & Heavy Metal Testing Lab Certificate IDs<br/>"
                      "• Quarantine Status (True / False)", table_cell_style),
            Paragraph("NABL-accredited cosmetic lab testing reports", table_cell_style),
            Paragraph("<b>Regulatory & Quarantine Protection:</b> Batches flagged in quarantine cannot be allocated to orders until QA manager releases them with an immutable audit log entry.", table_cell_style)
        ],
        [
            Paragraph("<b>Current Physical Stock Count</b>", table_cell_bold),
            Paragraph("• Exact count of undamaged, sealed units per Batch at each Warehouse Location", table_cell_style),
            Paragraph("Physical inventory stock audit count sheet", table_cell_style),
            Paragraph("<b>Initial Ledger Baseline:</b> Populates the source-of-truth <code>InventoryLedger</code> table and synchronizes sellable quantities to Shopify, Amazon, and Flipkart.", table_cell_style)
        ]
    ]

    t5 = Table([headers5] + rows5, colWidths=[90, 135, 120, 178])
    t5.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t5)
    story.append(PageBreak())

    # SECTION 6: B2B Wholesaler, Stockist & Distributor Registry
    story.append(Paragraph("6. B2B Wholesaler, Stockist & Retailer Profile Directory", h1_style))
    story.append(Paragraph("Powers B2B wholesale pricing, credit risk governance, tiered volume discounts, and GST-compliant B2B invoices.", body_style))
    story.append(Spacer(1, 4))

    headers6 = [
        Paragraph("Wholesale Field", table_header_style),
        Paragraph("Specification & Required Details", table_header_style),
        Paragraph("Example Data", table_header_style),
        Paragraph("Operational Purpose & Business Impact", table_header_style),
    ]

    rows6 = [
        [
            Paragraph("<b>Entity Name & Trade Name</b>", table_cell_bold),
            Paragraph("Full legal entity name matching GST registration certificate", table_cell_style),
            Paragraph("Glow & Pure Wellness Retail LLP", table_cell_style),
            Paragraph("Printed on B2B GST Tax Invoices and Delivery Challans.", table_cell_style)
        ],
        [
            Paragraph("<b>GSTIN (15 characters)</b>", table_cell_bold),
            Paragraph("Statutory 15-digit alphanumeric Indian GSTIN", table_cell_style),
            Paragraph("<code>27AAPFU0939F1ZV</code>", table_cell_code),
            Paragraph("Enforces GST portal verification, determines CGST+SGST vs IGST tax split, and qualifies B2B e-Invoices.", table_cell_style)
        ],
        [
            Paragraph("<b>Trade & Cosmetic Licenses</b>", table_cell_bold),
            Paragraph("• State Shop & Establishment License<br/>"
                      "• Cosmetic Wholesale License (Form 20B/21B)", table_cell_style),
            Paragraph("<code>MH-FDA-20B-78812</code>", table_cell_code),
            Paragraph("Compliance verification under Indian Drugs and Cosmetics Act for cosmetic wholesale distribution.", table_cell_style)
        ],
        [
            Paragraph("<b>Billing & Delivery Coordinates</b>", table_cell_bold),
            Paragraph("Registered billing address and physical warehouse delivery address with PIN code", table_cell_style),
            Paragraph("Bhiwandi Logistics Park, Unit 12, Thane, MH - 421302", table_cell_style),
            Paragraph("Required for e-Way Bill generation, distance-based freight slabs, and delivery dispatch.", table_cell_style)
        ],
        [
            Paragraph("<b>Wholesale Tier</b>", table_cell_bold),
            Paragraph("Categorization: <code>RETAILER</code>, <code>STOCKIST</code>, <code>SUPER_STOCKIST</code>, <code>INSTITUTIONAL</code>", table_cell_style),
            Paragraph("<code>STOCKIST</code>", table_cell_code),
            Paragraph("Determines whether standard PTR (e.g. 25% margin) or super-stockist PTS (e.g. 40% margin) applies.", table_cell_style)
        ],
        [
            Paragraph("<b>Credit Limit & Period</b>", table_cell_bold),
            Paragraph("Approved maximum outstanding balance (₹) and repayment window (days)", table_cell_style),
            Paragraph("Limit: ₹5,00,000<br/>Period: 45 days", table_cell_style),
            Paragraph("Blocks order confirmation if wholesaler exceeds credit threshold or has overdue unpaid invoices.", table_cell_style)
        ],
        [
            Paragraph("<b>Invoice Discount Preferences</b>", table_cell_bold),
            Paragraph("• Discount Mode (Percentage vs Flat ₹)<br/>"
                      "• Show Discount on Invoice (True / False)", table_cell_style),
            Paragraph("<code>PERCENTAGE</code>, <code>True</code>", table_cell_code),
            Paragraph("Controls whether trade/promotional discounts are itemized on the commercial invoice PDF.", table_cell_style)
        ]
    ]

    t6 = Table([headers6] + rows6, colWidths=[90, 135, 120, 178])
    t6.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t6)
    story.append(Spacer(1, 10))

    # SECTION 7: Financial Accounting Baseline & Fixed OPEX Ledger
    story.append(Paragraph("7. Financial Cost Accounting Baseline & Fixed OPEX Ledger", h1_style))
    story.append(Paragraph("Enables exact 6-tier P&L math: Formulation COGS (CM1), Logistics & Platform fees (CM2), Ad Spend (CM3), and Fixed OPEX (EBITDA).", body_style))
    story.append(Spacer(1, 4))

    headers7 = [
        Paragraph("Cost Component", table_header_style),
        Paragraph("Required Breakdown & Source", table_header_style),
        Paragraph("Typical Values / Frequency", table_header_style),
        Paragraph("Impact on CEO Financial Command Center", table_header_style),
    ]

    rows7 = [
        [
            Paragraph("<b>Itemized Unit Formulation COGS</b>", table_cell_bold),
            Paragraph("Per-SKU Bill of Materials (BOM):<br/>"
                      "• Active bulk mineral ingredients cost<br/>"
                      "• Primary packaging (glass dropper, pump, tube)<br/>"
                      "• Mono-carton, label sticker, induction foil<br/>"
                      "• Inward raw material transport cost", table_cell_style),
            Paragraph("Serum: ₹300/unit<br/>Cleanser: ₹180/unit<br/>Alum Stick: ₹120/unit", table_cell_style),
            Paragraph("<b>CM1 Calculation:</b> Landed COGS is locked immutably at dispatch to compute true Gross Margin and protect the absolute cost floor.", table_cell_style)
        ],
        [
            Paragraph("<b>Secondary & Outer Packaging</b>", table_cell_bold),
            Paragraph("Cost per dispatch:<br/>"
                      "• Corrugated master shipper carton<br/>"
                      "• Bubble wrap, kraft honeycomb paper<br/>"
                      "• Pura Stone branded tamper-evident security tape", table_cell_style),
            Paragraph("D2C: ₹15–₹25/order<br/>B2B Carton: ₹45–₹65/carton", table_cell_style),
            Paragraph("<b>CM2 Packaging Overheads:</b> Automatically added to variable fulfillment cost on every dispatched package.", table_cell_style)
        ],
        [
            Paragraph("<b>Monthly Fixed OPEX Ledger</b>", table_cell_bold),
            Paragraph("Itemized monthly operating expenses:<br/>"
                      "• Executive & Staff Payroll (Salaries, PF, ESI)<br/>"
                      "• Warehouse & Office Rent / Lease agreements<br/>"
                      "• SaaS Subscriptions (Shopify, ERP, AWS, Klaviyo)<br/>"
                      "• Utilities (Electricity, High-speed internet)<br/>"
                      "• Legal, Regulatory & CA Audit Retainers", table_cell_style),
            Paragraph("Monthly Ledger entries (e.g. ₹8,50,000 / month)", table_cell_style),
            Paragraph("<b>EBITDA & Cash Runway:</b> Deducts fixed operational burn from CM3 to produce true monthly EBITDA, Net Profit, and Net Cash Flow runway in months.", table_cell_style)
        ],
        [
            Paragraph("<b>FEFO Batch Write-Offs & Wastage</b>", table_cell_bold),
            Paragraph("Cost records of expired batches, transit breakage, R&D formulation pilot batches, or quality rejects", table_cell_style),
            Paragraph("Logged on incident occurrence with photo evidence", table_cell_style),
            Paragraph("<b>Loss & Leakage Accounting:</b> Separates inventory write-offs from order fulfillment so product margins are not falsely distorted.", table_cell_style)
        ]
    ]

    t7 = Table([headers7] + rows7, colWidths=[90, 135, 120, 178])
    t7.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t7)
    story.append(Spacer(1, 10))

    # SECTION 8: Production Server Infrastructure Environment Variables
    story.append(Paragraph("8. Production Infrastructure & Cloud Environment Variables (.env)", h1_style))
    story.append(Paragraph("Required to configure production database clustering, Redis asynchronous task processing, and document storage.", body_style))
    story.append(Spacer(1, 4))

    headers8 = [
        Paragraph("Environment Variable", table_header_style),
        Paragraph("Expected Format / Security Level", table_header_style),
        Paragraph("Infrastructure Provider", table_header_style),
        Paragraph("System Function & Purpose", table_header_style),
    ]

    rows8 = [
        [
            Paragraph("<code>DATABASE_URL</code>", table_cell_code),
            Paragraph("<code>postgres://user:pass@host:5432/purastone_db</code>", table_cell_code),
            Paragraph("AWS RDS / Supabase / Neon / Local PostgreSQL 16", table_cell_style),
            Paragraph("Primary high-availability transactional database storing all inventory, orders, and ledgers.", table_cell_style)
        ],
        [
            Paragraph("<code>REDIS_URL</code>", table_cell_code),
            Paragraph("<code>redis://:auth_token@host:6379/0</code>", table_cell_code),
            Paragraph("Upstash / AWS ElastiCache / Redis Cloud", table_cell_style),
            Paragraph("Message broker for Celery async tasks: PDF invoice rendering, marketplace stock sync, and daily backups.", table_cell_style)
        ],
        [
            Paragraph("<code>AWS_S3_MEDIA_BUCKET</code>", table_cell_code),
            Paragraph("Bucket Name, Access Key ID, Secret Access Key", table_cell_code),
            Paragraph("Amazon S3 / Cloudflare R2 / MinIO", table_cell_style),
            Paragraph("AES-256 encrypted object storage for generated Tax Invoice PDFs, COA compliance documents, and signed LRs.", table_cell_style)
        ],
        [
            Paragraph("<code>SECRET_KEY & ALLOWED_HOSTS</code>", table_cell_code),
            Paragraph("64-char crypto string & domain list", table_cell_code),
            Paragraph("Production Server Settings", table_cell_style),
            Paragraph("Cryptographic signing of JWT tokens, CSRF protection, and authorized host domain filtering.", table_cell_style)
        ]
    ]

    t8 = Table([headers8] + rows8, colWidths=[95, 130, 120, 178])
    t8.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t8)
    story.append(Spacer(1, 12))

    # Action Checklist Summary Box
    checklist_html = (
        "<b>NEXT OPERATIONAL ACTION STEPS FOR PURA STONE TEAM:</b><br/>"
        "<b>Step 1:</b> Export existing SKU directory with dimensions, barcodes, MRP, PTR, and formulation COGS into Excel/CSV.<br/>"
        "<b>Step 2:</b> Conduct physical stock take to record current unit counts by Batch ID, Mfg Date, and Expiry Date.<br/>"
        "<b>Step 3:</b> Gather verified GSTIN certificates, wholesale licenses, and credit limits for existing retail stockists.<br/>"
        "<b>Step 4:</b> Generate API keys from Shopify, Amazon SP-API, and Razorpay partner dashboards as detailed in Section 1.<br/>"
        "<b>Step 5:</b> Provide monthly OPEX figures (Rent, Payroll, SaaS) to activate real-time EBITDA and Cash Runway tracking."
    )
    checklist_table = Table([[Paragraph(checklist_html, body_style)]], colWidths=[523])
    checklist_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#0f766e")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(checklist_table)

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated onboarding PDF: {filename}")

if __name__ == '__main__':
    filename = sys.argv[1] if len(sys.argv) > 1 else "PURA_STONE_DATA_ONBOARDING_AND_INTEGRATION_GUIDE.pdf"
    build_pdf(filename)
