import os
import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
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
            self.drawString(36, A4[1] - 25, "PURA STONE ENTERPRISE ERP — MASTER ONBOARDING, API KEYS & HOSTING GUIDE")
            self.drawRightString(A4[0] - 36, A4[1] - 25, "CONFIDENTIAL & PROPRIETARY")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(36, A4[1] - 28, A4[0] - 36, A4[1] - 28)

        # Footer (All pages)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 32, A4[0] - 36, 32)
        self.drawString(36, 20, "Pura Stone Mineral Skincare — Executive Implementation, API Manual & Hosting Handover")
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

    # Typography & Color Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10
    )

    h1_style = ParagraphStyle(
        'SectionHeading1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#0f766e"), # Pura Stone Teal
        spaceBefore=11,
        spaceAfter=5,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SectionHeading2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12.5,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1e293b")
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9.2,
        textColor=colors.HexColor("#1e293b")
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9.2,
        textColor=colors.HexColor("#0f172a")
    )

    table_cell_code = ParagraphStyle(
        'TableCellCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor("#0f766e")
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.8,
        textColor=colors.HexColor("#0369a1")
    )

    alert_style = ParagraphStyle(
        'AlertText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.8,
        textColor=colors.HexColor("#92400e")
    )

    green_callout_style = ParagraphStyle(
        'GreenCalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.8,
        textColor=colors.HexColor("#166534")
    )

    story = []

    # Title Banner
    story.append(Paragraph("PURA STONE ENTERPRISE ERP & FINANCIAL COMMAND CENTER", title_style))
    story.append(Paragraph(
        "<b>MASTER DATA ONBOARDING, API INTEGRATION MANUAL & INFRASTRUCTURE HANDOVER SPECIFICATION</b><br/>"
        "<i>Complete Step-by-Step API Key Generation Manual, VPS Hosting Credentials Handover, Database Plans & Pricing, Master Catalog Tables, and Financial Baseline Requirements.</i>",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f766e"), spaceAfter=8))

    # Executive Summary Box
    summary_html = (
        "<b>EXECUTIVE PURPOSE & INTEGRATION ARCHITECTURE:</b><br/>"
        "The Pura Stone ERP calculates automated real-time unit economics across a strict 6-tier waterfall: "
        "<b>GMV → Net Revenue → CM1 → CM2 → CM3 → EBITDA & Net Profit</b>. To transition from the current "
        "synthetic testing environment into 100% live production, the engineering and DevOps teams require exact operational credentials and master records across <b>10 core domains</b>:<br/>"
        "• <b>Sections 1 & 2:</b> Step-by-Step API Key Generation Guides for Shopify, Amazon SP-API, Flipkart, Razorpay, Stripe, Meta Ads, Google Ads, Logistics & GST APIs.<br/>"
        "• <b>Section 3:</b> Production VPS Hosting Platform Handover — Required Server Credentials, Recommended Specifications & Pricing Comparison (Hostinger, Hetzner, DigitalOcean, AWS).<br/>"
        "• <b>Section 4:</b> Production Database Services Handover — Self-Hosted PostgreSQL (₹0 Extra) vs. Managed Cloud DB (Supabase / Neon / AWS RDS) with Cost Breakdowns.<br/>"
        "• <b>Section 5:</b> Domain, DNS & SSL Configuration Handover (Cloudflare / Registrar).<br/>"
        "• <b>Section 6:</b> Cloud Object Storage for Invoices, LRs, and COAs (S3 / Cloudflare R2).<br/>"
        "• <b>Sections 7–10:</b> Master Skincare Catalog, Warehouse Batch Stock, B2B Wholesaler Directory, and Fixed OPEX Baseline."
    )
    summary_table = Table([[Paragraph(summary_html, callout_style)]], colWidths=[523])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#bae6fd")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 1: Step-by-Step Omnichannel & Payment API Key Generation Guide
    # =========================================================================
    story.append(Paragraph("1. Step-by-Step API Key Generation Guide: Omnichannel Marketplaces & Payment Gateways", h1_style))
    story.append(Paragraph(
        "Follow these exact step-by-step instructions in your partner dashboards to generate and provide the live production API keys required for automated order ingestion, fee reconciliation, and payment settlement.",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers1 = [
        Paragraph("Platform / Channel", table_header_style),
        Paragraph("Required Keys & Parameters", table_header_style),
        Paragraph("Step-by-Step Generation Instructions in Portal", table_header_style),
        Paragraph("System Function in Pura Stone ERP", table_header_style),
    ]

    rows1 = [
        [
            Paragraph("<b>Shopify Admin API</b><br/>(D2C Storefront)", table_cell_bold),
            Paragraph(
                "• <code>Admin API Access Token</code> (starts with <code>shpat_...</code>)<br/>"
                "• <code>API Key & Secret Key</code><br/>"
                "• <code>Store Domain</code> (e.g. <code>purastone.myshopify.com</code>)<br/>"
                "• <code>Webhook Signing Secret</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to Shopify Admin (<code>admin.shopify.com</code>).<br/>"
                "<b>2.</b> Go to <b>Settings</b> (bottom left gear) > <b>Apps and sales channels</b> > <b>Develop apps</b>.<br/>"
                "<b>3.</b> Click <b>Create an app</b> > Name: <code>PuraStone ERP Integration</code>.<br/>"
                "<b>4.</b> Click <b>Configure Admin API scopes</b> > Select: <code>read_products</code>, <code>write_products</code>, <code>read_orders</code>, <code>write_orders</code>, <code>read_inventory</code>, <code>write_inventory</code>, <code>read_fulfillments</code>, <code>read_locations</code>.<br/>"
                "<b>5.</b> Click <b>Install app</b> > Click <b>Reveal token once</b> and immediately copy the token (it is shown only once!).<br/>"
                "<b>6.</b> Under Webhooks, add endpoint: <code>https://api.purastone.com/api/finance/webhooks/shopify/</code> for events: <code>orders/create</code>, <code>orders/updated</code>, <code>orders/cancelled</code>.",
                table_cell_style
            ),
            Paragraph("Automates real-time order pull, multi-batch FEFO inventory reduction, bundle SKU translation, and tracking number back-sync.", table_cell_style)
        ],
        [
            Paragraph("<b>Amazon SP-API</b><br/>(India Marketplace)", table_cell_bold),
            Paragraph(
                "• <code>LWA Client ID</code><br/>"
                "• <code>LWA Client Secret</code><br/>"
                "• <code>LWA Refresh Token</code><br/>"
                "• <code>AWS Access Key & Secret</code><br/>"
                "• <code>SP-API Role ARN</code><br/>"
                "• <code>Marketplace ID: A21TJRUUN4KGV</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to Amazon Seller Central India (<code>sellercentral.amazon.in</code>).<br/>"
                "<b>2.</b> Go to <b>Partner Network</b> / <b>Apps & Services</b> > <b>Develop Apps</b>.<br/>"
                "<b>3.</b> Register a Developer Profile (Select: Pricing, Order Management, Finance & Accounting, Inventory).<br/>"
                "<b>4.</b> Click <b>Add new app client</b> > Name: <code>PuraStone-SPAPI</code> > Select SP-API.<br/>"
                "<b>5.</b> Copy the <b>LWA Client ID</b> and <b>LWA Client Secret</b>.<br/>"
                "<b>6.</b> In the Developer Central list, click <b>Authorize</b> next to the app to generate the permanent <b>Refresh Token</b>.<br/>"
                "<b>7.</b> In your AWS IAM Console, create an IAM Role with an inline policy for <code>execute-api</code>, attach to IAM user, and copy the <b>Role ARN</b> and AWS Access/Secret keys.",
                table_cell_style
            ),
            Paragraph("Ingests Amazon FBA & MFN orders, referral fees, closing fees, weight-handling charges, and bi-weekly bank disbursement UTRs.", table_cell_style)
        ],
        [
            Paragraph("<b>Flipkart Seller API</b><br/>(Marketplace)", table_cell_bold),
            Paragraph(
                "• <code>Application ID (App ID)</code><br/>"
                "• <code>Application Secret</code><br/>"
                "• <code>OAuth Bearer / Refresh Token</code><br/>"
                "• <code>Flipkart Seller ID</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to Flipkart Seller Hub (<code>seller.flipkart.com</code>).<br/>"
                "<b>2.</b> Go to <b>Settings</b> > <b>API Developer Portal</b> / <b>Self-Serve Applications</b>.<br/>"
                "<b>3.</b> Click <b>Register New Application</b> > Select scopes: <code>Orders</code>, <code>Listings</code>, <code>Returns</code>, <code>Settlements</code>.<br/>"
                "<b>4.</b> Copy the generated <b>App ID</b> and <b>App Secret</b>.<br/>"
                "<b>5.</b> Authorize application to retrieve the persistent OAuth Refresh Token and Seller ID.",
                table_cell_style
            ),
            Paragraph("Ingests orders, platform marketplace commission deductions, collection fees, reverse RTO shipping, and NEFT payout settlement sheets.", table_cell_style)
        ],
        [
            Paragraph("<b>Razorpay Payment Gateway</b><br/>(Live Mode)", table_cell_bold),
            Paragraph(
                "• <code>Key ID</code> (<code>rzp_live_...</code>)<br/>"
                "• <code>Key Secret</code><br/>"
                "• <code>Webhook Secret</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to Razorpay Dashboard (<code>dashboard.razorpay.com</code>).<br/>"
                "<b>2.</b> Ensure <b>Live Mode</b> toggle is activated on the top bar.<br/>"
                "<b>3.</b> Go to <b>Settings</b> (left navigation menu) > <b>API Keys</b> tab.<br/>"
                "<b>4.</b> Click <b>Generate Key</b> (or Regenerate Key) > Copy <b>Key ID</b> and <b>Key Secret</b>.<br/>"
                "<b>5.</b> Go to <b>Settings</b> > <b>Webhooks</b> > Click <b>Add New Webhook</b> > Enter URL: <code>https://api.purastone.com/api/finance/webhooks/razorpay/</code> > Select active events: <code>order.paid</code>, <code>payment.captured</code>, <code>payment.failed</code>, <code>refund.processed</code> > Copy the <b>Webhook Secret</b>.",
                table_cell_style
            ),
            Paragraph("Captures exact 2.0% + GST transaction fees, Net Settled payouts, payment mode splits (UPI vs Card vs Netbanking), and customer refunds.", table_cell_style)
        ],
        [
            Paragraph("<b>Stripe Payment Gateway</b><br/>(Global & Domestic)", table_cell_bold),
            Paragraph(
                "• <code>Publishable Key</code> (<code>pk_live_...</code>)<br/>"
                "• <code>Secret Key</code> (<code>sk_live_...</code>)<br/>"
                "• <code>Webhook Signing Secret</code> (<code>whsec_...</code>)",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to Stripe Dashboard (<code>dashboard.stripe.com</code>).<br/>"
                "<b>2.</b> Navigate to <b>Developers</b> (top right) > <b>API keys</b> tab.<br/>"
                "<b>3.</b> Copy the standard <b>Publishable key</b>.<br/>"
                "<b>4.</b> Under Secret keys, click <b>Reveal live key</b> and copy the <b>Secret key</b>.<br/>"
                "<b>5.</b> Go to <b>Developers</b> > <b>Webhooks</b> > Click <b>Add endpoint</b> > Enter Endpoint URL: <code>https://api.purastone.com/api/finance/webhooks/stripe/</code> > Select events: <code>checkout.session.completed</code>, <code>charge.refunded</code> > Copy <b>Signing secret</b>.",
                table_cell_style
            ),
            Paragraph("Calculates international transaction processing fees, cross-border currency conversion surcharges, and bank payout reconciliation.", table_cell_style)
        ]
    ]

    t1 = Table([headers1] + rows1, colWidths=[90, 115, 200, 118])
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

    # =========================================================================
    # SECTION 2: Step-by-Step Ad Platform, Logistics & Government APIs
    # =========================================================================
    story.append(Paragraph("2. Step-by-Step API Key Generation: Ad Networks, Logistics & GST E-Way Bill", h1_style))
    story.append(Paragraph(
        "Required to power CM3 attribution (Meta/Google Ad spend) and TMS freight allocation (Shiprocket/Delhivery/NIC e-Way Bill).",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers2 = [
        Paragraph("Integration Service", table_header_style),
        Paragraph("Required Keys & IDs", table_header_style),
        Paragraph("Step-by-Step Generation Instructions in Portal", table_header_style),
        Paragraph("System Function & Mathematical Impact", table_header_style),
    ]

    rows2 = [
        [
            Paragraph("<b>Meta Marketing API</b><br/>(FB & Instagram Ads)", table_cell_bold),
            Paragraph(
                "• <code>System User Access Token</code><br/>"
                "• <code>Ad Account ID</code> (<code>act_...</code>)<br/>"
                "• <code>App ID & App Secret</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Open Meta for Developers (<code>developers.facebook.com</code>) & Meta Business Suite.<br/>"
                "<b>2.</b> Go to <b>Business Settings</b> > <b>Users</b> > <b>System Users</b> > Click <b>Add</b> (Assign Admin role).<br/>"
                "<b>3.</b> Click <b>Assign Assets</b> > Select your Facebook Ad Account & Instagram Business Account > Toggle <b>Manage Campaigns</b>.<br/>"
                "<b>4.</b> Click <b>Generate New Token</b> > Select App > Scopes: <code>ads_read</code>, <code>read_insights</code> > Set Token Expiration: <b>Never</b>.<br/>"
                "<b>5.</b> Copy the generated token and your numeric <b>Ad Account ID</b>.",
                table_cell_style
            ),
            Paragraph("Deducts daily Meta ad spend against D2C revenue to calculate channel-specific <b>CM3</b> and Blended ROAS.", table_cell_style)
        ],
        [
            Paragraph("<b>Google Ads API</b><br/>(Search, PMax & YouTube)", table_cell_bold),
            Paragraph(
                "• <code>Developer Token</code><br/>"
                "• <code>OAuth Client ID & Secret</code><br/>"
                "• <code>Refresh Token</code><br/>"
                "• <code>Customer ID</code> (<code>XXX-XXX-XXXX</code>)",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Go to Google Cloud Console (<code>console.cloud.google.com</code>) > Create Project > Enable <b>Google Ads API</b>.<br/>"
                "<b>2.</b> Under Credentials, create <b>OAuth 2.0 Client ID</b> (Web App) > Save Client ID and Secret.<br/>"
                "<b>3.</b> In Google Ads Manager Account (<code>ads.google.com</code>) > <b>Tools & Settings</b> > <b>API Center</b> > Copy <b>Developer Token</b>.<br/>"
                "<b>4.</b> Complete OAuth authorization flow to generate permanent Refresh Token > Copy Google Ads Customer ID.",
                table_cell_style
            ),
            Paragraph("Ingests Google performance advertising costs, linking cost-per-click to SKU conversion to determine true marketing contribution.", table_cell_style)
        ],
        [
            Paragraph("<b>Logistics Aggregator</b><br/>(Shiprocket / Delhivery)", table_cell_bold),
            Paragraph(
                "• <code>API User Email & Password</code><br/>"
                "• <code>Bearer Authentication Token</code><br/>"
                "• <code>Account / Client Code</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to Shiprocket / Delhivery One corporate dashboard.<br/>"
                "<b>2.</b> Go to <b>Settings</b> > <b>API</b> / <b>Integrations</b> > <b>API Details</b>.<br/>"
                "<b>3.</b> Generate API User credentials > Copy <b>User Email</b> and <b>API Password</b> (or permanent API Token).",
                table_cell_style
            ),
            Paragraph("Pulls forward shipping charges, RTO reverse penalty costs, COD collection fees, and proof of delivery (POD) tracking.", table_cell_style)
        ],
        [
            Paragraph("<b>GST e-Way Bill & E-Invoice</b><br/>(NIC Portal / GSP)", table_cell_bold),
            Paragraph(
                "• <code>GSP User ID & Password</code><br/>"
                "• <code>GSP Client ID & Secret</code><br/>"
                "• <code>Company GSTIN</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>1.</b> Log in to National e-Way Bill Portal (<code>ewaybillgst.gov.in</code>).<br/>"
                "<b>2.</b> Go to <b>Registration</b> > <b>For GSP</b> > Register GSP User Credentials.<br/>"
                "<b>3.</b> If using an authorized GSP partner (ClearTax/Masters India), copy their Client ID & Secret credentials.",
                table_cell_style
            ),
            Paragraph("Automates generation of statutory e-Way Bills and QR-code IRN e-invoices for B2B wholesale consignments exceeding ₹50,000.", table_cell_style)
        ]
    ]

    t2 = Table([headers2] + rows2, colWidths=[90, 115, 200, 118])
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

    # =========================================================================
    # SECTION 3: Production VPS Hosting Server Handover & Plan Recommendations
    # =========================================================================
    story.append(Paragraph("3. Production VPS Hosting Server Handover & Plan Recommendations", h1_style))
    story.append(Paragraph(
        "To deploy and host your Pura Stone ERP, background task scheduler (Celery/Redis), and automated database backups with 99.9% uptime, "
        "the engineering team requires administrative access to your VPS hosting platform.",
        body_style
    ))
    story.append(Spacer(1, 4))

    vps_alert_html = (
        "<b>ACTION REQUIRED FROM PURA STONE TEAM:</b><br/>"
        "Please provide the <b>Login ID (Email/Username) and Password</b> for your Cloud VPS hosting provider, "
        "OR create an account with one of the recommended providers below and share server SSH access:<br/>"
        "• <b>Hosting Control Panel URL</b> (e.g., Hostinger / Hetzner / DigitalOcean dashboard)<br/>"
        "• <b>Account Username & Password</b> (or invite <code>dev@purastone.com</code> / our technical team as Admin)<br/>"
        "• <b>Server IP Address & SSH Port</b> (Default: Port 22)<br/>"
        "• <b>Root Username & Password</b> (or SSH Public Key access)<br/>"
        "• <b>Target Operating System:</b> <b>Ubuntu 22.04 LTS or 24.04 LTS (64-bit)</b>"
    )
    vps_alert_table = Table([[Paragraph(vps_alert_html, alert_style)]], colWidths=[523])
    vps_alert_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#fde68a")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(vps_alert_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Recommended VPS Hosting Plans & Pricing Comparison for Pura Stone ERP:", h2_style))

    headers_vps = [
        Paragraph("Hosting Provider", table_header_style),
        Paragraph("Recommended Plan & Specs", table_header_style),
        Paragraph("Estimated Monthly Pricing", table_header_style),
        Paragraph("Data Center & Architecture Fit for Pura Stone", table_header_style),
    ]

    rows_vps = [
        [
            Paragraph("<b>Hostinger VPS</b><br/>(Top Recommended for India)", table_cell_bold),
            Paragraph(
                "<b>Plan: KVM 2 (Recommended Baseline)</b><br/>"
                "• 2 vCPU Cores<br/>"
                "• 8 GB RAM<br/>"
                "• 100 GB NVMe Disk Space<br/>"
                "• 8 TB Bandwidth<br/>"
                "• 1 Dedicated IPv4 Address",
                table_cell_style
            ),
            Paragraph(
                "<b>₹599 – ₹899 / month</b><br/>"
                "(~$7 – $11 / month)<br/>"
                "<i>Billed annually: ~₹7,188/yr</i>",
                table_cell_bold
            ),
            Paragraph(
                "<b>Mumbai, India Data Center.</b><br/>"
                "Lowest latency for Indian B2B wholesalers and D2C traffic. Easily handles Django (3 Gunicorn worker replicas) + React Vite frontend + Redis + Celery + self-hosted PostgreSQL.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>Hostinger VPS</b><br/>(High-Volume Scale)", table_cell_bold),
            Paragraph(
                "<b>Plan: KVM 4 (High Scale)</b><br/>"
                "• 4 vCPU Cores<br/>"
                "• 16 GB RAM<br/>"
                "• 200 GB NVMe Disk Space<br/>"
                "• 16 TB Bandwidth",
                table_cell_style
            ),
            Paragraph(
                "<b>₹1,199 – ₹1,499 / month</b><br/>"
                "(~$14 – $18 / month)<br/>"
                "<i>Billed annually: ~₹14,388/yr</i>",
                table_cell_bold
            ),
            Paragraph(
                "<b>Recommended when monthly order volume exceeds 5,000+ orders.</b> "
                "Provides massive headroom for high-frequency ReportLab vector PDF invoice generation and concurrent FEFO warehouse queries.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>Hetzner Cloud</b><br/>(Industry Benchmark Performance)", table_cell_bold),
            Paragraph(
                "<b>Plan: CPX31 (Dedicated AMD)</b><br/>"
                "• 4 vCPU (AMD EPYC)<br/>"
                "• 8 GB RAM<br/>"
                "• 160 GB NVMe SSD<br/>"
                "• 20 TB Traffic",
                table_cell_style
            ),
            Paragraph(
                "<b>€14.50 / month</b><br/>"
                "(~₹1,320 / month)<br/>"
                "<i>Pay-as-you-go hourly</i>",
                table_cell_bold
            ),
            Paragraph(
                "<b>Falkenstein / Helsinki / Ashburn.</b><br/>"
                "Extreme price-to-performance ratio with dedicated AMD EPYC server cores. Exceptional reliability and automated snapshot backups.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>DigitalOcean</b><br/>(Developer Cloud)", table_cell_bold),
            Paragraph(
                "<b>Plan: Premium AMD Droplet</b><br/>"
                "• 2 vCPU Cores<br/>"
                "• 4 GB RAM (or 8 GB: $48/mo)<br/>"
                "• 80 GB NVMe SSD",
                table_cell_style
            ),
            Paragraph(
                "<b>$24.00 – $48.00 / month</b><br/>"
                "(~₹2,000 – ₹4,000 / month)",
                table_cell_bold
            ),
            Paragraph(
                "<b>Bangalore, India (BLR1) Data Center.</b><br/>"
                "Established developer platform with seamless 1-click snapshot backups and floating IP failover.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>AWS EC2</b><br/>(Enterprise Scalability)", table_cell_bold),
            Paragraph(
                "<b>Plan: t4g.xlarge (ARM Graviton2)</b><br/>"
                "• 4 vCPU Cores<br/>"
                "• 16 GB RAM<br/>"
                "• EBS gp3 Storage",
                table_cell_style
            ),
            Paragraph(
                "<b>~$65.00 – $85.00 / month</b><br/>"
                "(~₹5,500 – ₹7,200 / month)",
                table_cell_bold
            ),
            Paragraph(
                "<b>Mumbai (ap-south-1).</b> Enterprise tier with AWS CloudWatch monitoring, VPC isolation, and integration with AWS RDS.",
                table_cell_style
            )
        ]
    ]

    t_vps = Table([headers_vps] + rows_vps, colWidths=[90, 130, 115, 188])
    t_vps.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_vps)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 4: Production Database Services Handover, Architectures & Pricing
    # =========================================================================
    story.append(Paragraph("4. Production Database Services Handover, Architecture Options & Pricing", h1_style))
    story.append(Paragraph(
        "Pura Stone ERP uses PostgreSQL 16 with pessimistic row-locking (<code>select_for_update()</code>) to guarantee zero inventory overselling. "
        "You can choose between an included self-hosted database or a managed cloud database service.",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers_db = [
        Paragraph("Database Architecture Option", table_header_style),
        Paragraph("Service Provider & Plan", table_header_style),
        Paragraph("Monthly Cost", table_header_style),
        Paragraph("Required Credentials from Client & Architecture Details", table_header_style),
    ]

    rows_db = [
        [
            Paragraph("<b>OPTION A: Self-Hosted PostgreSQL 16</b><br/>(Top Recommended — Zero Extra Cost)", table_cell_bold),
            Paragraph("<b>Runs directly on your VPS Server</b><br/>Configured with PgBouncer connection pooling and local NVMe storage.", table_cell_style),
            Paragraph("<b>₹0 / month</b><br/>(Included inside VPS hosting plan)", table_cell_bold),
            Paragraph(
                "<b>NO EXTERNAL CREDENTIALS REQUIRED.</b><br/>"
                "Our team configures PostgreSQL 16 on your VPS with an automated cron job that dumps the database daily, encrypts it with AES-256, and uploads it to secure off-site cloud storage (Cloudflare R2/S3). Most cost-effective solution.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>OPTION B1: Supabase Pro</b><br/>(Managed Cloud Database)", table_cell_bold),
            Paragraph(
                "<b>Supabase Pro Tier</b><br/>"
                "• Dedicated PostgreSQL 15/16<br/>"
                "• 8 GB Database Storage (expandable)<br/>"
                "• Built-in PgBouncer Pooling<br/>"
                "• Daily Automated Backups (7-day retention)",
                table_cell_style
            ),
            Paragraph("<b>$25.00 / month</b><br/>(~₹2,100 / month)", table_cell_bold),
            Paragraph(
                "<b>Credentials to Provide:</b><br/>"
                "• Supabase Dashboard Login (Email & Password)<br/>"
                "• Database Connection String (URI):<br/>"
                "<code>postgres://postgres.[ref]:[pass]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres</code><br/>"
                "• Direct Database Password",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>OPTION B2: Neon Serverless Postgres</b><br/>(Auto-Scaling Cloud DB)", table_cell_bold),
            Paragraph(
                "<b>Neon Launch / Scale Plan</b><br/>"
                "• Serverless Postgres with instant branching<br/>"
                "• Point-in-time recovery<br/>"
                "• Dedicated compute endpoints",
                table_cell_style
            ),
            Paragraph("<b>$19.00 / month</b><br/>(~₹1,600 / month)", table_cell_bold),
            Paragraph(
                "<b>Credentials to Provide:</b><br/>"
                "• Neon Cloud Console Login (Email & Password)<br/>"
                "• Pooled Connection String (Host, User, Password, DB Name)",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>OPTION B3: AWS RDS PostgreSQL</b><br/>(Enterprise Managed)", table_cell_bold),
            Paragraph(
                "<b>AWS RDS db.t4g.medium</b><br/>"
                "• 2 vCPU, 4 GB RAM<br/>"
                "• Multi-AZ automated failover<br/>"
                "• Automated AWS snapshot patching",
                table_cell_style
            ),
            Paragraph("<b>~$45.00 – $60.00 / month</b><br/>(~₹3,800 – ₹5,000 / month)", table_cell_bold),
            Paragraph(
                "<b>Credentials to Provide:</b><br/>"
                "• AWS Management Console Login or IAM User with RDS Admin permissions.<br/>"
                "• RDS Endpoint URL, Master Username, and Master Password.",
                table_cell_style
            )
        ]
    ]

    t_db = Table([headers_db] + rows_db, colWidths=[105, 120, 95, 203])
    t_db.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_db)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 5: Domain, DNS, SSL & Cloud Storage Handover
    # =========================================================================
    story.append(Paragraph("5. Domain, DNS, SSL & Cloud Object Storage Credentials Handover", h1_style))
    story.append(Paragraph(
        "To bind your live custom domain, issue automated SSL/TLS certificates, and store generated PDF invoices, the team requires the following access:",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers_dns = [
        Paragraph("Infrastructure Layer", table_header_style),
        Paragraph("Required Credentials / Access", table_header_style),
        Paragraph("Recommended Provider & Pricing", table_header_style),
        Paragraph("Subdomain Routing & Function", table_header_style),
    ]

    rows_dns = [
        [
            Paragraph("<b>DNS & Domain Registrar</b><br/>(Cloudflare / GoDaddy / Namecheap)", table_cell_bold),
            Paragraph(
                "• Domain Registrar / Cloudflare Login (Email & Password)<br/>"
                "• OR invite developer as DNS Administrator in Cloudflare.",
                table_cell_style
            ),
            Paragraph(
                "<b>Cloudflare Free Tier (₹0)</b><br/>"
                "Top recommended. Includes free automatic SSL/TLS, edge caching, DDoS mitigation, and Brotli compression.",
                table_cell_style
            ),
            Paragraph(
                "Routes traffic to:<br/>"
                "• <code>app.purastone.com</code> (React ERP Frontend)<br/>"
                "• <code>api.purastone.com</code> (Django REST API & Webhooks)<br/>"
                "• <code>tms.purastone.com</code> (Wholesale & Driver Tracking)",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>Cloud Storage for PDFs & Documents</b><br/>(Invoices, LRs & COAs)", table_cell_bold),
            Paragraph(
                "• S3 / R2 Account ID<br/>"
                "• <code>Access Key ID</code><br/>"
                "• <code>Secret Access Key</code><br/>"
                "• Bucket Name: <code>purastone-docs-prod</code>",
                table_cell_code
            ),
            Paragraph(
                "<b>Cloudflare R2 (₹0 – ₹150/mo)</b><br/>"
                "10 GB free storage, zero egress bandwidth fees.<br/>"
                "<i>AWS S3 alternative: ~$2 – $5/mo.</i>",
                table_cell_style
            ),
            Paragraph(
                "Permanent AES-256 encrypted storage for generated Tax Invoices, Lorry Receipts (LR), Certificates of Analysis (COA), and dispatch packing slips.",
                table_cell_style
            )
        ]
    ]

    t_dns = Table([headers_dns] + rows_dns, colWidths=[105, 135, 115, 168])
    t_dns.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_dns)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 6: Master Skincare Catalog & Omnichannel SKU Mapping
    # =========================================================================
    story.append(Paragraph("6. Master Skincare Catalog & Omnichannel SKU Directory", h1_style))
    story.append(Paragraph(
        "Required to map internal Pura Stone formulations to external marketplace identifiers (Shopify Variant ID, Amazon ASIN/SellerSKU, Flipkart FSN). "
        "Please provide an Excel or CSV file containing these columns:",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers_sku = [
        Paragraph("Field Name", table_header_style),
        Paragraph("Data Type / Example", table_header_style),
        Paragraph("Source / Department", table_header_style),
        Paragraph("System Function & Business Impact", table_header_style),
    ]

    rows_sku = [
        [
            Paragraph("<code>internal_sku</code>", table_cell_code),
            Paragraph("String: <code>PURA-ALUM-ROLLON-100</code>", table_cell_style),
            Paragraph("R&D / Brand Master", table_cell_style),
            Paragraph("Primary foreign key uniting physical batches, B2B wholesale orders, and marketplace settlements.", table_cell_style)
        ],
        [
            Paragraph("<code>product_name & line</code>", table_cell_code),
            Paragraph("String: <i>Natural Alum Deodorant 100g (Core Mineral)</i>", table_cell_style),
            Paragraph("Marketing / Catalog", table_cell_style),
            Paragraph("Display name printed on GST Tax Invoices, Transporter Lorry Receipts, and Master Carton Labels.", table_cell_style)
        ],
        [
            Paragraph("<code>mrp, ptr & pts</code>", table_cell_code),
            Paragraph("Decimal (INR): <code>999.00 / 750.00 / 600.00</code>", table_cell_style),
            Paragraph("Sales & Commercials", table_cell_style),
            Paragraph("Enforces wholesale pricing tiers (Tier A/B/C) and prevents orders from falling below minimum margin floors.", table_cell_style)
        ],
        [
            Paragraph("<code>formulation_cogs & pack_cost</code>", table_cell_code),
            Paragraph("Decimal (INR): <code>185.50 / 45.00</code>", table_cell_style),
            Paragraph("Cost Accounting / Lab", table_cell_style),
            Paragraph("Subtracted from Net Revenue to compute exact <b>CM1 (Contribution Margin 1)</b>.", table_cell_style)
        ],
        [
            Paragraph("<code>shopify_variant_id</code>", table_cell_code),
            Paragraph("Numeric: <code>44981298410291</code>", table_cell_code),
            Paragraph("Shopify Storefront", table_cell_style),
            Paragraph("Direct webhook matching for real-time inventory allocation upon customer checkout.", table_cell_style)
        ],
        [
            Paragraph("<code>amazon_asin & seller_sku</code>", table_cell_code),
            Paragraph("String: <code>B09X1Y2Z3A / PURA-ALUM-FBA</code>", table_cell_code),
            Paragraph("Amazon Seller Central", table_cell_style),
            Paragraph("Links Amazon SP-API Order Reports to formulation batch inventory and settlement fees.", table_cell_style)
        ],
        [
            Paragraph("<code>flipkart_fsn</code>", table_cell_code),
            Paragraph("String: <code>SKUFC8912781920</code>", table_cell_code),
            Paragraph("Flipkart Seller Hub", table_cell_style),
            Paragraph("Matches Flipkart Seller Settlement API records against physical stock dispatches.", table_cell_style)
        ],
        [
            Paragraph("<code>hsn_code & gst_rate</code>", table_cell_code),
            Paragraph("String: <code>33049990</code> | Decimal: <code>18.00%</code>", table_cell_style),
            Paragraph("Tax & Finance", table_cell_style),
            Paragraph("Calculates IGST (inter-state) vs CGST+SGST (intra-state) splits on all tax invoices.", table_cell_style)
        ],
        [
            Paragraph("<code>dimensions & gross_weight</code>", table_cell_code),
            Paragraph("L×W×H (cm): <code>12×5×5</code> | Weight: <code>140g</code>", table_cell_style),
            Paragraph("Packaging Master", table_cell_style),
            Paragraph("Computes volumetric weight vs dead weight in the TMS freight engine for accurate shipping quotes.", table_cell_style)
        ]
    ]

    t_sku = Table([headers_sku] + rows_sku, colWidths=[105, 125, 105, 188])
    t_sku.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_sku)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 7: Physical Warehouse Locations & Live FEFO Batch Inventory
    # =========================================================================
    story.append(Paragraph("7. Physical Warehouse Locations & Live FEFO Batch Traceability", h1_style))
    story.append(Paragraph(
        "To populate the live stock ledger, please provide current physical inventory count by warehouse location, formulation batch, and expiry dates.",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers_inv = [
        Paragraph("Warehouse / Location Dimension", table_header_style),
        Paragraph("Field Format / Example", table_header_style),
        Paragraph("Operational Meaning", table_header_style),
        Paragraph("System Enforcement", table_header_style),
    ]

    rows_inv = [
        [
            Paragraph("<code>Warehouse Identifier</code>", table_cell_code),
            Paragraph("<code>WH-MUM-CENTRAL</code> (Bhiwandi Hub)", table_cell_style),
            Paragraph("Central Fulfillment & Dispatch Hub", table_cell_style),
            Paragraph("Determines origin state GSTIN for tax invoices and origin pincode for freight calculation.", table_cell_style)
        ],
        [
            Paragraph("<code>Aisle, Row, Shelf, Bin</code>", table_cell_code),
            Paragraph("<code>Aisle: A-02, Row: 03, Shelf: S-01, Bin: B-04</code>", table_cell_style),
            Paragraph("Exact Physical Storage Coordinates", table_cell_style),
            Paragraph("Guides pickers directly to the physical shelf during dispatch, preventing search delays.", table_cell_style)
        ],
        [
            Paragraph("<code>Batch ID & Mfg Date</code>", table_cell_code),
            Paragraph("<code>BAT-2026-MUM-01</code> | <code>2026-04-10</code>", table_cell_style),
            Paragraph("Manufacturing Lot Identifier", table_cell_style),
            Paragraph("Mandatory on cosmetic labels under Indian Drugs and Cosmetics Rules for quality tracing.", table_cell_style)
        ],
        [
            Paragraph("<code>Expiry Date (FEFO Key)</code>", table_cell_code),
            Paragraph("<code>2027-10-10</code> (ISO 8601)", table_cell_style),
            Paragraph("Product Expiration Date", table_cell_style),
            Paragraph("Strict chronological sorting: closest-to-expire batches are allocated first; near-expiry (<60 days) batches are locked from B2B wholesale.", table_cell_style)
        ],
        [
            Paragraph("<code>Batch Landed COGS</code>", table_cell_code),
            Paragraph("Decimal (INR): <code>182.40 / unit</code>", table_cell_style),
            Paragraph("Actual Formulation Cost of Lot", table_cell_style),
            Paragraph("Enables exact batch-wise COGS calculation rather than broad monthly averages.", table_cell_style)
        ]
    ]

    t_inv = Table([headers_inv] + rows_inv, colWidths=[110, 135, 120, 158])
    t_inv.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_inv)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 8: B2B Wholesaler, Stockist & Distributor Registry
    # =========================================================================
    story.append(Paragraph("8. B2B Wholesaler, Stockist & Distributor Registry", h1_style))
    story.append(Paragraph(
        "Required to onboard existing commercial wholesale partners, configure tier discount matrices, credit limits, and branch child IDs.",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers_b2b = [
        Paragraph("Wholesaler Master Field", table_header_style),
        Paragraph("Validation Rule / Format", table_header_style),
        Paragraph("Example Record", table_header_style),
        Paragraph("Business Impact & ERP Workflow", table_header_style),
    ]

    rows_b2b = [
        [
            Paragraph("<code>Legal Company Name</code>", table_cell_code),
            Paragraph("String (as registered on MCA/GST)", table_cell_style),
            Paragraph("Aura Wellness Retail Pvt Ltd", table_cell_style),
            Paragraph("Legal parent entity holding credit terms and master contracts.", table_cell_style)
        ],
        [
            Paragraph("<code>Parent GSTIN</code>", table_cell_code),
            Paragraph("15-char regex: <code>^[0-9]{2}[A-Z]{5}...</code>", table_cell_code),
            Paragraph("<code>27AABCA1234F1Z5</code>", table_cell_code),
            Paragraph("Validates registered tax status and determines inter-state vs intra-state invoice taxation.", table_cell_style)
        ],
        [
            Paragraph("<code>Trade / Cosmetic License</code>", table_cell_code),
            Paragraph("Form 20B/21B Drug License #", table_cell_style),
            Paragraph("<code>DL-MH-MUM-2026-991</code>", table_cell_code),
            Paragraph("Compliance check before authorizing bulk mineral skincare dispatches.", table_cell_style)
        ],
        [
            Paragraph("<code>Credit Limit & Period</code>", table_cell_code),
            Paragraph("Amount in INR & Days", table_cell_style),
            Paragraph("₹5,00,000 limit & 30 days net", table_cell_style),
            Paragraph("Blocks dispatch when outstanding ledger balance exceeds credit limit.", table_cell_style)
        ],
        [
            Paragraph("<code>Pricing Tier Slabs</code>", table_cell_code),
            Paragraph("Tier A / B / C or Custom Matrix", table_cell_style),
            Paragraph("Tier A (100–499 pcs: 25% off MRP)", table_cell_style),
            Paragraph("Automatically prices wholesale orders with floor margin protection.", table_cell_style)
        ],
        [
            Paragraph("<code>Retail Branch Stores (Child IDs)</code>", table_cell_code),
            Paragraph("Store ID, Address, Branch GSTIN", table_cell_style),
            Paragraph("<code>AURA-MUM-01</code> (Bandra West Flagship)", table_cell_style),
            Paragraph("Enables branch-specific delivery challans, Transporter LRs, and tracking logins.", table_cell_style)
        ]
    ]

    t_b2b = Table([headers_b2b] + rows_b2b, colWidths=[110, 115, 120, 178])
    t_b2b.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_b2b)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 9: Financial Accounting Baseline & Fixed OPEX Ledger
    # =========================================================================
    story.append(Paragraph("9. Financial Accounting Baseline, Formulation Costs & Fixed OPEX Ledger", h1_style))
    story.append(Paragraph(
        "To activate the CEO Financial Command Center and calculate real-time EBITDA, Net Profit, and Cash Runway, provide the following monthly fixed costings:",
        body_style
    ))
    story.append(Spacer(1, 4))

    headers_opex = [
        Paragraph("OPEX Expense Category", table_header_style),
        Paragraph("Frequency / Baseline Value", table_header_style),
        Paragraph("Expense Bucket in ERP", table_header_style),
        Paragraph("P&L Mathematical Impact", table_header_style),
    ]

    rows_opex = [
        [
            Paragraph("<b>Warehouse & Fulfillment Lease</b>", table_cell_bold),
            Paragraph("Monthly Lease (e.g. ₹1,20,000/mo)", table_cell_style),
            Paragraph("<code>WAREHOUSE_RENT_OPS</code>", table_cell_code),
            Paragraph("Subtracted from CM3 to calculate true Operating EBITDA.", table_cell_style)
        ],
        [
            Paragraph("<b>Core Payroll & Staff Wages</b>", table_cell_bold),
            Paragraph("Monthly Net Payroll (e.g. ₹3,50,000/mo)", table_cell_style),
            Paragraph("<code>PAYROLL_SALARIES</code>", table_cell_code),
            Paragraph("Fixed operational overhead allocated across the calendar month.", table_cell_style)
        ],
        [
            Paragraph("<b>Software, Cloud Hosting & SaaS</b>", table_cell_bold),
            Paragraph("Monthly Cloud Costs (e.g. ₹25,000/mo)", table_cell_style),
            Paragraph("<code>SAAS_TECH_SOFTWARE</code>", table_cell_code),
            Paragraph("Deducted from monthly gross profit to track software burn rate.", table_cell_style)
        ],
        [
            Paragraph("<b>PR Seeding & Complimentary Testers</b>", table_cell_bold),
            Paragraph("Actual Formulation Cost (INR)", table_cell_style),
            Paragraph("<code>TESTER_PR_SEEDING</code>", table_cell_code),
            Paragraph("Deducted in <b>CM3</b> to account for influencer marketing product costs.", table_cell_style)
        ],
        [
            Paragraph("<b>Opening Liquid Cash & Bank Balances</b>", table_cell_bold),
            Paragraph("Total Available Cash in INR", table_cell_style),
            Paragraph("<code>OPENING_CASH_BALANCE</code>", table_cell_code),
            Paragraph("Divided by monthly Net Burn Rate to compute exact <b>Cash Runway in Months</b>.", table_cell_style)
        ]
    ]

    t_opex = Table([headers_opex] + rows_opex, colWidths=[110, 115, 120, 178])
    t_opex.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t_opex)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 10: Master Action Checklist & Secure Transmission Protocol
    # =========================================================================
    story.append(Paragraph("10. Master Onboarding Action Checklist & Secure Handover Protocol", h1_style))
    story.append(Paragraph(
        "Please follow this sequence to securely provide credentials and data files to our implementation team:",
        body_style
    ))
    story.append(Spacer(1, 4))

    action_html = (
        "<b>OFFICIAL STEP-BY-STEP HANDOVER CHECKLIST:</b><br/>"
        "<b>1. VPS Hosting Platform:</b> Share your Hostinger / Hetzner / DigitalOcean control panel login or server root SSH access (Section 3).<br/>"
        "<b>2. Database Services:</b> Confirm whether you want included Self-Hosted PostgreSQL 16 (₹0 extra) or share Managed DB credentials (Section 4).<br/>"
        "<b>3. Omnichannel APIs:</b> Generate and copy API credentials from Shopify, Amazon SP-API, Flipkart, and Razorpay using the step-by-step guides in Section 1.<br/>"
        "<b>4. Ad Accounts & Logistics:</b> Generate Meta Marketing API token and logistics credentials as detailed in Section 2.<br/>"
        "<b>5. Master Catalog & Stock Take:</b> Export your product master table (Section 6) and initial physical batch stock counts (Section 7) into Excel/CSV.<br/>"
        "<b>6. Wholesale Directory & OPEX:</b> Share list of active B2B stockists (Section 8) and monthly fixed costs (Section 9).<br/><br/>"
        "<b>SECURE CREDENTIALS TRANSMISSION PROTOCOL:</b><br/>"
        "To ensure maximum security, <b>never send production passwords or API secrets in plain text over unencrypted chat</b>. "
        "Please transmit all credentials using one of the following secure methods:<br/>"
        "• <b>Option A (Preferred):</b> Share via a password-protected, self-destructing link using <b>Bitwarden Send</b> or <b>1Password</b>.<br/>"
        "• <b>Option B:</b> Encrypted ZIP archive with an AES-256 password sent via a separate channel (e.g. Signal / SMS).<br/>"
        "• <b>Option C:</b> Directly invite our technical team email to your Shopify, Meta, Amazon, and Hosting accounts with Developer/Admin privileges."
    )
    action_table = Table([[Paragraph(action_html, green_callout_style)]], colWidths=[523])
    action_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#bbf7d0")),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
    ]))
    story.append(action_table)

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated updated onboarding PDF: {filename}")


if __name__ == '__main__':
    filename = sys.argv[1] if len(sys.argv) > 1 else "PURA_STONE_DATA_ONBOARDING_AND_INTEGRATION_GUIDE.pdf"
    build_pdf(filename)
