# PURASTONE &bull; Omnichannel IMS & B2B Wholesaler Management Hub

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://www.djangoproject.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev/)
[![Celery](https://img.shields.io/badge/Celery-5.6-37814A?logo=celery)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Redis-8.1-DC382D?logo=redis)](https://redis.io/)
[![ReportLab](https://img.shields.io/badge/ReportLab-5.1-F58220)](https://www.reportlab.com/)

An enterprise-grade, omnichannel Inventory Management System (IMS) and B2B Wholesaler Hub built for **PURASTONE Natural Care & Mineral Logistics**. Built with Python, Django REST Framework, Celery, Redis, and React (Vite).

---

## 🌟 Key Architectural Features

### 1. Database & Core Inventory Engine
- **Relational Ledger Architecture:** `Product Master`, `Batch & Expiry`, `Location Master` (Warehouse, Aisle, Row, Shelf, Bin), and `InventoryLedger`.
- **Append-Only Immutable Audit Trail:** `TransactionLog` protected by database signals that block updates and deletions (`UPDATE` and `DELETE` raises exceptions).
- **Strict FEFO Outtake Logic:** First-Expiring, First-Out algorithm that routes dispatch to the nearest-expiring sellable batch and returns precise shelf/bin picking directives.
- **Manual Stock Adjustments:** Required reason codes (e.g. `INFLUENCER_SEEDING`, `DAMAGED_IN_TRANSIT`, `EXPIRED_DISPOSAL`).
- **Promotional BOGO & Bundle Decomposition:** Decomposes promotional SKUs into actual base product deductions via `BundleMapping`.
- **Database Row-Level Concurrency:** `select_for_update()` on inventory ledgers to strictly prevent race conditions and overselling across channels.

### 2. Async Marketplace Integrations & Rate Limiting
- **Supported Channels:** Shopify, Amazon (SP-API), Flipkart.
- **Async Queueing via Celery & Redis:** Dedicated rate limiters (Leaky/Token Bucket) that prevent API throttling without blocking main web threads.

### 3. Integrated B2B Wholesaler Management Hub
- **Parent-Child Entity Architecture:**
  - `WholesalerParent`: Master legal corporate entity (GSTIN, legal name, verification queue).
  - `WholesalerChild`: Specific physical retail branches/agents with distinct login credentials.
- **Immutable Historical Cost Ledger:** `locked_base_cost` (COGS) and `locked_b2b_price` captured into `WholesaleOrderItem` upon drafting to insulate historical profitability from catalog price changes.
- **Multi-Product Order Builder:**
  - Select approved master and branch (auto-populates legal details and shipping addresses).
  - Add multiple products to a single order.
  - Manual entry for unit price per piece and GST percentage per line item.
  - Automatic sequential PO / Order Reference generation.
- **Admin Custom Discount Engine:**
  - Flat (₹) or percentage (%) discount approvals.
  - **Negative Margin Floor Guard:** Strictly blocks discounts that reduce the order's final value below total base COGS.
- **Automated Tax Invoicing (PDF):**
  - Order confirmation triggers async Celery task generating branded PDF tax invoices via ReportLab.
- **Profit Margin Yield Dashboards:**
  - Real-time aggregation of active accounts, total revenue, total COGS, net profit, and margin yields.

---

## 🖥️ ERP Navigation & Module Layout

The UI implements a high-density ERP interface following the **PURASTONE** brand identity (Burnt Clay `#a05a3a`, Soft Linen `#f5e9dd`, Cormorant Garamond serif, Outfit sans-serif) with keyboard shortcut support (`F1` to `F13`):

```
[GATEWAY OF INVENTORY]
[F1]  Inventory Executive Dashboard    → Comprehensive warehouse health & valuation
[F2]  Real-Time Stock Breakdown        → Batch & shelf ledger table
[F3]  Inbound Stock Intake             → Inbound intake form & shelf bin allocation
[F4]  FEFO Outtake & Routing           → Nearest-expiry pick directives
[F5]  Manual Stock Adjustment          → Mandatory reason code adjustments
[F6]  BOGO & Omnichannel Orders        → Bundle decomposition & channel sync
[F7]  Immutable Audit Trail            → Append-only database ledger

[GATEWAY OF WHOLESALER]
[F8]  Wholesaler Executive Dashboard   → B2B revenue, profit & yield analytics
[F9]  Create Wholesale Order          → Multi-product builder with manual price & GST
[F10] B2B Orders & Discount Desk       → Margin-floor discount engine & FEFO fulfill
[F11] Master Onboarding & Approval     → GSTIN review & verification queue
[F12] Branch & Child ID Portal         → Store/agent login generator
[F13] B2B Invoices & PDFs              → Celery async tax invoice archive
```

---

## 🚀 Quickstart & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- Redis (optional for local testing; memory bucket fallback included)

### 1. Backend Setup (Django & Celery)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed demo data (products, batches, wholesaler accounts)
python manage.py seed_demo_data

# Run Django development server
python manage.py runserver 127.0.0.1:8000
```

### 2. Frontend Setup (React & Vite)

```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```

The frontend will run at `http://127.0.0.1:5173/` and connect to the backend at `http://127.0.0.1:8000/`.

---

## 🧪 Running the Test Suite

Execute the test suite covering concurrency, FEFO allocation, BOGO decomposition, wholesaler parent-child relations, negative margin protection, and Celery invoice tasks:

```bash
python manage.py test
```

All 19 tests pass:
```
Ran 19 tests in 42.419s: OK
```

