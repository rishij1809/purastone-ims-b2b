import React, { useState, useEffect } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000/api';

// Purastone Signature Botanical Line-Art Emblem
function PurastoneLogoSmall() {
  return (
    <svg
      className="purastone-emblem-small"
      viewBox="0 0 160 210"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect
        x="28"
        y="18"
        width="104"
        height="164"
        rx="52"
        stroke="currentColor"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
      <g stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M 28 42 C 22 36, 12 32, 6 36 C 8 28, 16 22, 28 26" />
        <path d="M 18 32 C 14 20, 24 12, 32 18" />
        <path d="M 24 38 C 16 42, 14 52, 22 56 C 26 50, 26 44, 28 42" />
        <circle cx="10" cy="46" r="2" fill="currentColor" />
        <circle cx="34" cy="12" r="2" fill="currentColor" />
      </g>
      <g stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M 132 158 C 138 164, 148 168, 154 164 C 152 172, 144 178, 132 174" />
        <path d="M 142 168 C 146 180, 136 188, 128 182" />
        <path d="M 136 162 C 144 158, 146 148, 138 144 C 134 150, 134 156, 132 158" />
        <circle cx="150" cy="154" r="2" fill="currentColor" />
        <circle cx="126" cy="188" r="2" fill="currentColor" />
      </g>
      <path
        d="M 68 62 C 64 62, 54 64, 48 74 C 42 84, 44 94, 46 98 C 48 100, 46 104, 44 108 C 42 112, 46 116, 52 116 C 56 116, 58 124, 62 128 C 66 132, 70 134, 76 132"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M 52 88 Q 58 86 64 88" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      <path
        d="M 86 94 C 82 92, 74 96, 72 104 C 70 114, 72 122, 74 128 C 76 136, 74 144, 72 154 C 74 158, 80 162, 86 162 C 92 162, 94 158, 98 152 C 104 142, 106 132, 102 124 C 98 116, 96 104, 94 96"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M 82 118 Q 88 116 92 120" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M 84 136 Q 90 138 94 134" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

// Smart Auto-Generator for B2B Wholesale Purchase Order Reference
function generateAutoPoNumber(storeId) {
  const year = new Date().getFullYear();
  let prefix = 'PURA';
  if (storeId) {
    const parts = storeId.split('-');
    prefix = parts[0] || 'PURA';
  }
  const randomSuffix = Math.floor(100 + Math.random() * 900);
  return `PO-${prefix.toUpperCase()}-${year}-${randomSuffix}`;
}

export default function App() {
  const [activeTab, setActiveTab] = useState('inv_dashboard');
  const [inventory, setInventory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);

  // Wholesaler Data States
  const [wholesalerParents, setWholesalerParents] = useState([]);
  const [wholesalerChildren, setWholesalerChildren] = useState([]);
  const [wholesaleOrders, setWholesaleOrders] = useState([]);
  const [wholesaleAnalytics, setWholesaleAnalytics] = useState(null);
  const [selectedParentAnalytics, setSelectedParentAnalytics] = useState(null);

  // Core IMS Intake Form State
  const [intakeForm, setIntakeForm] = useState({
    sku: 'PURA-ALUM-ROLLON-100',
    quantity: 50,
    batch_id: 'BATCH-PURA-' + Math.floor(100 + Math.random() * 900),
    mfg_date: new Date().toISOString().split('T')[0],
    expiry_date: new Date(Date.now() + 240 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    warehouse: 'CENTRAL_WH',
    aisle: 'A1',
    row: 'R1',
    shelf: 'S01',
    bin: 'B01',
  });

  // Core IMS Outtake Form State
  const [outtakeForm, setOuttakeForm] = useState({
    sku: 'PURA-ALUM-ROLLON-100',
    quantity: 6,
    source: 'MANUAL',
  });
  const [outtakeResult, setOuttakeResult] = useState(null);

  // Manual Adjustment State
  const [adjustForm, setAdjustForm] = useState({
    sku: 'PURA-ALUM-ROLLON-100',
    batch_id: '',
    location_id: '',
    quantity_change: -2,
    reason_code: 'INFLUENCER_SEEDING',
  });

  // BOGO / Omnichannel Order State
  const [orderForm, setOrderForm] = useState({
    order_id: 'ORD-PURA-' + Math.floor(10000 + Math.random() * 90000),
    source: 'SHOPIFY',
    sku: 'PROMO-BOGO-PURASTONE',
    quantity: 2,
  });
  const [orderResult, setOrderResult] = useState(null);

  // Wholesaler Module Forms State
  const [onboardForm, setOnboardForm] = useState({
    name: '',
    gstin: '',
    master_email: '',
  });

  const [childForm, setChildForm] = useState({
    parent_id: '',
    branch_name: '',
    store_id: '',
    shipping_address: '',
    contact_person: '',
    username: '',
    password: 'Wholesale@123',
  });

  const [newOrderForm, setNewOrderForm] = useState({
    child_id: '',
    po_number: generateAutoPoNumber(''),
    notes: '',
    items: [
      {
        sku: 'PURA-ALUM-ROLLON-100',
        quantity: 10,
        unit_price: '450.00',
        gst_percentage: '18.00',
      },
    ],
  });

  const [discountForm, setDiscountForm] = useState({
    order_id: '',
    discount_type: 'PERCENTAGE',
    discount_value: 10,
  });

  const showNotice = (msg, isError = false) => {
    setNotification({ msg, isError });
    setTimeout(() => setNotification(null), 6000);
  };

  // Fetch Core IMS Data
  const fetchInventory = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/inventory/`);
      if (res.ok) {
        const data = await res.json();
        setInventory(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTransactions = async () => {
    try {
      const res = await fetch(`${API_BASE}/transactions/`);
      if (res.ok) {
        const data = await res.json();
        setTransactions(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Fetch Wholesaler Module Data
  const fetchWholesalerData = async () => {
    try {
      const [pRes, cRes, oRes, aRes] = await Promise.all([
        fetch(`${API_BASE}/wholesale/parents/`),
        fetch(`${API_BASE}/wholesale/children/`),
        fetch(`${API_BASE}/wholesale/orders/`),
        fetch(`${API_BASE}/wholesale/analytics/`),
      ]);
      if (pRes.ok) setWholesalerParents(await pRes.json());
      if (cRes.ok) setWholesalerChildren(await cRes.json());
      if (oRes.ok) setWholesaleOrders(await oRes.json());
      if (aRes.ok) setWholesaleAnalytics(await aRes.json());
    } catch (err) {
      console.error('Error fetching wholesaler data:', err);
    }
  };

  useEffect(() => {
    fetchInventory();
    fetchTransactions();
    fetchWholesalerData();

    // ERP Keyboard Shortcuts (F1 to F13)
    const handleKeyDown = (e) => {
      const keyMap = {
        F1: 'inv_dashboard',
        F2: 'inventory',
        F3: 'intake',
        F4: 'outtake',
        F5: 'adjust',
        F6: 'order',
        F7: 'logs',
        F8: 'ws_dashboard',
        F9: 'ws_create_order',
        F10: 'ws_orders',
        F11: 'ws_onboard',
        F12: 'ws_children',
        F13: 'ws_invoices',
      };
      if (keyMap[e.key]) {
        e.preventDefault();
        setActiveTab(keyMap[e.key]);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Handlers for Core IMS
  const handleIntakeSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/intake/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...intakeForm, quantity: parseInt(intakeForm.quantity, 10) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed intake');
      showNotice(`Inbound verified: ${data.quantity_added} units received into batch ${data.batch_id}`);
      fetchInventory();
      fetchTransactions();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleOuttakeSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setOuttakeResult(null);
    try {
      const res = await fetch(`${API_BASE}/outtake/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...outtakeForm, quantity: parseInt(outtakeForm.quantity, 10) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed outtake');
      setOuttakeResult(data);
      showNotice(`FEFO Allocation complete: ${data.total_deducted} units routed to shelf.`);
      fetchInventory();
      fetchTransactions();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleAdjustSubmit = async (e) => {
    e.preventDefault();
    if (!adjustForm.reason_code.trim()) {
      showNotice('Reason code is strictly mandatory for manual adjustments.', true);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/adjust/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...adjustForm, quantity_change: parseInt(adjustForm.quantity_change, 10) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed adjustment');
      showNotice(`Adjustment recorded: ${data.quantity_change} units [${data.reason_code}]`);
      fetchInventory();
      fetchTransactions();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleOrderSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setOrderResult(null);
    try {
      const res = await fetch(`${API_BASE}/order/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_id: orderForm.order_id,
          source: orderForm.source,
          items: [{ sku: orderForm.sku, quantity: parseInt(orderForm.quantity, 10) }],
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed order processing');
      setOrderResult(data);
      showNotice(`Order ${data.order_id} resolved & deducted via ${data.source}.`);
      fetchInventory();
      fetchTransactions();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  // Handlers for Wholesaler Module
  const handleOnboardSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/wholesale/parents/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(onboardForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed onboarding');
      showNotice(`Wholesaler registered: ${data.name} (Status: PENDING_APPROVAL)`);
      setOnboardForm({ name: '', gstin: '', master_email: '' });
      fetchWholesalerData();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleApproveParent = async (parentId) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/wholesale/parents/${parentId}/approve/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed approval');
      showNotice(`Wholesaler approved: ${data.name}`);
      fetchWholesalerData();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleChildSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/wholesale/children/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(childForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed branch creation');
      showNotice(`Branch login ID generated: ${data.branch_name} (${data.username})`);
      setChildForm({
        parent_id: '',
        branch_name: '',
        store_id: '',
        shipping_address: '',
        contact_person: '',
        username: '',
        password: 'Wholesale@123',
      });
      fetchWholesalerData();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleWsOrderSubmit = async (e) => {
    e.preventDefault();
    if (!newOrderForm.child_id) {
      showNotice('Please select an approved wholesaler branch.', true);
      return;
    }
    if (!newOrderForm.items || newOrderForm.items.length === 0) {
      showNotice('Please add at least one product item.', true);
      return;
    }
    for (let i = 0; i < newOrderForm.items.length; i++) {
      const it = newOrderForm.items[i];
      if (!it.sku) {
        showNotice(`Please select product on line ${i + 1}`, true);
        return;
      }
      if (!it.quantity || parseInt(it.quantity, 10) <= 0) {
        showNotice(`Please enter valid quantity for line ${i + 1}`, true);
        return;
      }
      if (it.unit_price === '' || parseFloat(it.unit_price) < 0) {
        showNotice(`Please enter valid amount per piece for line ${i + 1}`, true);
        return;
      }
    }

    setLoading(true);
    try {
      const payload = {
        child_id: parseInt(newOrderForm.child_id, 10),
        po_number: newOrderForm.po_number,
        notes: newOrderForm.notes,
        items: newOrderForm.items.map((it) => ({
          sku: it.sku,
          quantity: parseInt(it.quantity, 10),
          unit_price: parseFloat(it.unit_price),
          gst_percentage: parseFloat(it.gst_percentage || 18.0),
        })),
      };

      const res = await fetch(`${API_BASE}/wholesale/orders/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed draft order');
      showNotice(
        `Draft Wholesale Order ${data.id.substring(0, 8)} locked in! Subtotal: ₹${data.subtotal}, Grand Total: ₹${data.grand_total || data.final_value}`
      );
      fetchWholesalerData();
      setActiveTab('ws_orders');
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyDiscount = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/wholesale/orders/${discountForm.order_id}/discount/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          discount_type: discountForm.discount_type,
          discount_value: parseFloat(discountForm.discount_value),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed discount');
      showNotice(`Approved discount of ₹${data.discount_amount} applied. Final Value: ₹${data.final_value} (Margin protected!)`);
      fetchWholesalerData();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmOrder = async (orderId) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/wholesale/orders/${orderId}/confirm/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed confirmation');
      showNotice(`Order confirmed! FEFO physical stock deducted & PDF invoice task dispatched.`);
      fetchInventory();
      fetchTransactions();
      fetchWholesalerData();
    } catch (err) {
      showNotice(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const handleViewParentAnalytics = async (parentId) => {
    try {
      const res = await fetch(`${API_BASE}/wholesale/analytics/${parentId}/`);
      if (res.ok) {
        setSelectedParentAnalytics(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Metric totals across inventory
  const totalStockCount = inventory.reduce((acc, curr) => acc + (curr.total_quantity || 0), 0);
  const totalSellableCount = inventory.reduce((acc, curr) => acc + (curr.sellable_quantity || 0), 0);
  const totalExpiredCount = inventory.reduce((acc, curr) => acc + (curr.expired_quantity || 0), 0);
  const totalMrpValuation = inventory.reduce((acc, curr) => acc + ((curr.total_quantity || 0) * (parseFloat(curr.base_price) || 0)), 0);
  const totalCogsValuation = inventory.reduce((acc, curr) => acc + ((curr.total_quantity || 0) * (parseFloat(curr.base_cost) || 0)), 0);

  const inventoryNavItems = [
    { id: 'inv_dashboard', keycode: '[F1]', label: 'Inventory Executive Dashboard' },
    { id: 'inventory', keycode: '[F2]', label: 'Real-Time Stock Breakdown' },
    { id: 'intake', keycode: '[F3]', label: 'Inbound Stock Intake' },
    { id: 'outtake', keycode: '[F4]', label: 'FEFO Outtake & Routing' },
    { id: 'adjust', keycode: '[F5]', label: 'Manual Stock Adjustment' },
    { id: 'order', keycode: '[F6]', label: 'BOGO & Omnichannel Orders' },
    { id: 'logs', keycode: '[F7]', label: 'Immutable Audit Trail' },
  ];

  const wholesalerNavItems = [
    { id: 'ws_dashboard', keycode: '[F8]', label: 'Wholesaler Executive Dashboard' },
    { id: 'ws_create_order', keycode: '[F9]', label: 'Create Wholesale Order' },
    { id: 'ws_orders', keycode: '[F10]', label: 'B2B Orders & Discount Desk' },
    { id: 'ws_onboard', keycode: '[F11]', label: 'Master Onboarding & Approval' },
    { id: 'ws_children', keycode: '[F12]', label: 'Branch & Child ID Portal' },
    { id: 'ws_invoices', keycode: '[F13]', label: 'B2B Invoices & PDFs' },
  ];

  return (
    <div className="erp-app-shell">
      {/* 1. TOP GLOBAL HEADER BAR */}
      <header className="erp-top-header">
        <div className="top-left-branding">
          <span className="erp-badge">[PURASTONE LOGISTICS IMS]</span>
          <span className="erp-company-name">
            PURASTONE NATURAL CARE & MINERAL LOGISTICS PVT. LTD.
          </span>
          <span className="erp-reg-info">
            IBA REG: PURA/2026/9841 &bull; GSTIN: 27AABCP1092F1Z8
          </span>
        </div>

        <div className="top-right-meta">
          <div className="header-select-pill">
            <span className="pill-tag">BRANCH:</span>
            <span className="pill-val">Central WH & Fulfillment Hub ▼</span>
          </div>
          <div className="header-select-pill user-pill">
            <span className="pill-tag">ROLE:</span>
            <span className="pill-val">Inventory & B2B Master (Full Access) ▼</span>
          </div>
        </div>
      </header>

      {/* 2. BODY LAYOUT: DOCKED SIDEBAR + MAIN WORKSPACE */}
      <div className="erp-body-layout">
        {/* LEFT SIDEBAR NAVIGATION */}
        <aside className="erp-sidebar">
          <div className="sidebar-brand-section">
            <PurastoneLogoSmall />
            <div className="sidebar-brand-text">
              <span className="sidebar-title">PURASTONE</span>
              <span className="sidebar-subtitle">ONLY WHAT YOU NEED</span>
            </div>
          </div>

          {/* SECTION 1: GATEWAY OF INVENTORY */}
          <div className="sidebar-section-heading">GATEWAY OF INVENTORY</div>
          <nav className="sidebar-nav-list">
            {inventoryNavItems.map((item) => (
              <button
                key={item.id}
                className={`sidebar-nav-item ${activeTab === item.id ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab(item.id);
                  if (item.id === 'inventory') fetchInventory();
                  if (item.id === 'logs') fetchTransactions();
                }}
              >
                <span className="nav-keycode">{item.keycode}</span>
                <span className="nav-label">{item.label}</span>
              </button>
            ))}
          </nav>

          {/* SECTION 2: GATEWAY OF WHOLESALER */}
          <div className="sidebar-section-heading wholesale-heading">GATEWAY OF WHOLESALER</div>
          <nav className="sidebar-nav-list">
            {wholesalerNavItems.map((item) => (
              <button
                key={item.id}
                className={`sidebar-nav-item ${activeTab === item.id ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab(item.id);
                  fetchWholesalerData();
                }}
              >
                <span className="nav-keycode">{item.keycode}</span>
                <span className="nav-label">{item.label}</span>
              </button>
            ))}
          </nav>

          {/* ASYNC RATE LIMIT STATUS WIDGET */}
          <div className="sidebar-channels-box">
            <div className="sidebar-channels-title">ASYNC RATE LIMIT STATUS</div>
            <div className="channel-rate-row">
              <span className="rate-channel">Shopify</span>
              <span className="rate-val">2.0 req/s [OK]</span>
            </div>
            <div className="channel-rate-row">
              <span className="rate-channel">Amazon SP-API</span>
              <span className="rate-val">2.0 req/s [OK]</span>
            </div>
            <div className="channel-rate-row">
              <span className="rate-channel">Flipkart</span>
              <span className="rate-val">5.0 req/s [OK]</span>
            </div>
          </div>

          {/* SIDEBAR FOOTER STATUS */}
          <div className="sidebar-footer-status">
            <div className="status-line">
              <span className="status-dot"></span> STATUS: <strong>ONLINE</strong>
            </div>
            <div className="status-line">
              DATE: <strong>{new Date().toLocaleDateString('en-GB')}</strong>
            </div>
            <div className="status-line engine-line">
              PURASTONE CORE ENGINE: <strong>v2.1.0 (B2B Active)</strong>
            </div>
          </div>
        </aside>

        {/* RIGHT MAIN WORKSPACE */}
        <main className="erp-main-content">
          {notification && (
            <div className={`erp-alert-banner ${notification.isError ? 'error' : 'success'}`}>
              <span className="alert-symbol">{notification.isError ? '⚠️' : '✦'}</span>
              <span>{notification.msg}</span>
            </div>
          )}

          {/* Module Banner Header */}
          <div className="erp-module-header">
            <span className="module-title-badge">
              MODULE: {[...inventoryNavItems, ...wholesalerNavItems].find((n) => n.id === activeTab)?.label.toUpperCase()} &bull; CENTRAL FULFILLMENT
            </span>
          </div>

          {/* Dynamic Tab Workspace */}
          <div className="erp-workspace-panel">
            {/* [F1] INVENTORY EXECUTIVE DASHBOARD */}
            {activeTab === 'inv_dashboard' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Executive Inventory Control & Stock Valuation Dashboard</h3>
                    <p className="subtext">
                      Central warehouse physical ledger health, FEFO readiness, valuation metrics, and marketplace synchronization status.
                    </p>
                  </div>
                  <button className="erp-btn-secondary" onClick={fetchInventory} disabled={loading}>
                    {loading ? 'Refreshing...' : '↻ Refresh Dashboard'}
                  </button>
                </div>

                {/* Primary Metric Deck for Inventory */}
                <section className="erp-metrics-deck" style={{ marginBottom: '22px' }}>
                  <div className="metric-box box-total">
                    <div className="metric-header">TOTAL AGGREGATE INVENTORY</div>
                    <div className="metric-value">{totalStockCount} <span className="unit">Units</span></div>
                    <div className="metric-sub">Physical warehouse count &bull; All Batches</div>
                  </div>

                  <div className="metric-box box-sellable">
                    <div className="metric-header">ACTIVE SELLABLE STOCK</div>
                    <div className="metric-value">{totalSellableCount} <span className="unit">Units</span></div>
                    <div className="metric-sub">Unexpired &bull; Ready for FEFO Dispatch</div>
                  </div>

                  <div className="metric-box box-expired">
                    <div className="metric-header">EXPIRED (QUARANTINED)</div>
                    <div className="metric-value">{totalExpiredCount} <span className="unit">Units</span></div>
                    <div className="metric-sub">Excluded from fulfillment &bull; Segregated</div>
                  </div>

                  <div className="metric-box box-health">
                    <div className="metric-header">FEFO COMPLIANCE & ACCURACY</div>
                    <div className="metric-value">100.0%</div>
                    <div className="metric-sub">Row locks active &bull; Overselling protected</div>
                  </div>
                </section>

                {/* Secondary Inventory Valuation Deck */}
                <div className="erp-metrics-deck" style={{ marginBottom: '22px' }}>
                  <div className="metric-box box-sellable">
                    <div className="metric-header">TOTAL STOCK VALUATION (AT B2C MRP)</div>
                    <div className="metric-value">₹{totalMrpValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                    <div className="metric-sub">Gross inventory retail market value</div>
                  </div>
                  <div className="metric-box box-total">
                    <div className="metric-header">TOTAL CAPITAL INVESTED (COGS)</div>
                    <div className="metric-value">₹{totalCogsValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                    <div className="metric-sub">Base production cost across physical units</div>
                  </div>
                  <div className="metric-box box-health">
                    <div className="metric-header">ACTIVE FORMULA CATALOG</div>
                    <div className="metric-value">{inventory.length} <span className="unit">SKUs</span></div>
                    <div className="metric-sub">Alum natural skincare product line</div>
                  </div>
                  <div className="metric-box box-expired">
                    <div className="metric-header">QUARANTINE RATIO</div>
                    <div className="metric-value">
                      {totalStockCount > 0 ? ((totalExpiredCount / totalStockCount) * 100).toFixed(1) : '0.0'}%
                    </div>
                    <div className="metric-sub">Segregated expired batch ratio</div>
                  </div>
                </div>

                {/* Dashboard Two-Column Grid */}
                <div className="dashboard-grid-two">
                  {/* Column 1: Batch Expiry Risk & Shelf Overview */}
                  <div className="erp-card-box">
                    <h4 className="box-title">Batch Shelf Distribution & Immediate Expiry Watch</h4>
                    <table className="erp-dense-table">
                      <thead>
                        <tr>
                          <th>SKU / PRODUCT</th>
                          <th>BATCH ID</th>
                          <th>EXPIRY</th>
                          <th>SHELF LOCATION</th>
                          <th>QTY</th>
                          <th>STATUS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inventory.flatMap(p => (p.batches || []).map(b => ({ ...b, sku: p.sku }))).slice(0, 6).map((b, bIdx) => (
                          <tr key={bIdx}>
                            <td><code>{b.sku}</code></td>
                            <td><strong>{b.batch_id}</strong></td>
                            <td>{b.expiry_date}</td>
                            <td>📍 {b.location?.display}</td>
                            <td><strong>{b.quantity}</strong></td>
                            <td>
                              <span className={`status-pill ${b.is_expired ? 'rejected' : 'approved'}`}>
                                {b.is_expired ? 'EXPIRED' : 'SELLABLE'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Column 2: Omnichannel Async Rate Limiters & Shortcuts */}
                  <div className="erp-card-box">
                    <h4 className="box-title">Marketplace Async Synchronization Health</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '16px' }}>
                      <div className="wholesaler-item-card">
                        <div className="item-meta-top">
                          <span className="item-name">Shopify Online Storefront</span>
                          <span className="status-pill approved">2.0 req/s &bull; HEALTHY</span>
                        </div>
                        <div className="item-details">
                          <span>Rate Protocol: Redis Leaky Bucket &bull; Celery Async Sync</span>
                          <span>Inventory Push: Real-time on intake/outtake commit</span>
                        </div>
                      </div>

                      <div className="wholesaler-item-card">
                        <div className="item-meta-top">
                          <span className="item-name">Amazon SP-API Marketplace</span>
                          <span className="status-pill approved">2.0 req/s &bull; HEALTHY</span>
                        </div>
                        <div className="item-details">
                          <span>Feed Type: JSON_LISTINGS_FEED &bull; Throttling protected</span>
                          <span>Auto Backoff: Exponential jitter on 429 response</span>
                        </div>
                      </div>

                      <div className="wholesaler-item-card">
                        <div className="item-meta-top">
                          <span className="item-name">Flipkart Commerce</span>
                          <span className="status-pill approved">5.0 req/s &bull; HEALTHY</span>
                        </div>
                        <div className="item-details">
                          <span>Listing Update API &bull; Strict concurrency locking</span>
                          <span>Database Lock: select_for_update() active</span>
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button className="erp-btn-primary" onClick={() => setActiveTab('intake')}>
                        → Inbound Intake [F3]
                      </button>
                      <button className="erp-btn-secondary" onClick={() => setActiveTab('outtake')}>
                        → FEFO Pick Directives [F4]
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
            {/* [F1] REAL-TIME STOCK BREAKDOWN */}
            {activeTab === 'inventory' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Live Omnichannel Stock & Shelf Ledger</h3>
                    <p className="subtext">
                      Real-time breakdown of Purastone natural alum formulas by batch, expiration date, and physical shelf coordinates.
                    </p>
                  </div>
                  <button className="erp-btn-secondary" onClick={fetchInventory} disabled={loading}>
                    {loading ? 'Refreshing...' : '↻ Refresh Stock Ledger'}
                  </button>
                </div>

                {inventory.length === 0 ? (
                  <div className="empty-panel-msg">No products found in ledger. Record an inbound intake to start.</div>
                ) : (
                  inventory.map((item) => (
                    <div key={item.sku} className="erp-sku-table-card">
                      <div className="sku-card-header">
                        <div className="sku-id-group">
                          <span className="sku-code-badge">{item.sku}</span>
                          <span className="sku-product-name">{item.product_name}</span>
                          <span className="sku-price">B2C: ₹{item.base_price} | B2B: ₹{item.default_b2b_price} | COGS: ₹{item.base_cost}</span>
                        </div>
                        <div className="sku-pills-group">
                          <span className="sku-stat-pill pill-total">Total: {item.total_quantity}</span>
                          <span className="sku-stat-pill pill-sellable">Sellable: {item.sellable_quantity}</span>
                          <span className="sku-stat-pill pill-expired">Quarantined: {item.expired_quantity}</span>
                        </div>
                      </div>

                      <table className="erp-dense-table">
                        <thead>
                          <tr>
                            <th>BATCH ID</th>
                            <th>MFG DATE</th>
                            <th>EXPIRY DATE</th>
                            <th>FEFO COMPLIANCE</th>
                            <th>EXACT SHELF LOCATION</th>
                            <th>QUANTITY</th>
                            <th>ACTIONS</th>
                          </tr>
                        </thead>
                        <tbody>
                          {item.batches.map((b) => (
                            <tr key={b.batch_id + b.location.id} className={b.is_expired ? 'row-expired' : 'row-active'}>
                              <td><strong>{b.batch_id}</strong></td>
                              <td>{b.mfg_date}</td>
                              <td><strong>{b.expiry_date}</strong></td>
                              <td>
                                {b.is_expired ? (
                                  <span className="status-badge-expired">EXPIRED / QUARANTINED</span>
                                ) : (
                                  <span className="status-badge-active">SELLABLE &bull; FEFO READY</span>
                                )}
                              </td>
                              <td><span className="erp-shelf-tag">📍 {b.location.display}</span></td>
                              <td><strong className="qty-emphasis">{b.quantity}</strong></td>
                              <td>
                                <button
                                  className="erp-action-btn"
                                  onClick={() => {
                                    setAdjustForm({
                                      sku: item.sku,
                                      batch_id: b.batch_id,
                                      location_id: b.location.id,
                                      quantity_change: -1,
                                      reason_code: 'INFLUENCER_SEEDING',
                                    });
                                    setActiveTab('adjust');
                                  }}
                                >
                                  Quick Adjust
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* [F2] INBOUND STOCK INTAKE */}
            {activeTab === 'intake' && (
              <div className="panel-inner form-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Inbound Inventory Intake</h3>
                    <p className="subtext">
                      Enters inbound goods into the single source of truth ledger with exact warehouse, aisle, row, and shelf coordinates.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleIntakeSubmit} className="erp-form-grid">
                  <div className="form-cell">
                    <label>PRODUCT SKU</label>
                    <input
                      type="text"
                      value={intakeForm.sku}
                      onChange={(e) => setIntakeForm({ ...intakeForm, sku: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>QUANTITY INBOUND</label>
                    <input
                      type="number"
                      min="1"
                      value={intakeForm.quantity}
                      onChange={(e) => setIntakeForm({ ...intakeForm, quantity: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>BATCH NUMBER / ID</label>
                    <input
                      type="text"
                      value={intakeForm.batch_id}
                      onChange={(e) => setIntakeForm({ ...intakeForm, batch_id: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>MANUFACTURING DATE</label>
                    <input
                      type="date"
                      value={intakeForm.mfg_date}
                      onChange={(e) => setIntakeForm({ ...intakeForm, mfg_date: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>EXPIRY DATE (FEFO SORT KEY)</label>
                    <input
                      type="date"
                      value={intakeForm.expiry_date}
                      onChange={(e) => setIntakeForm({ ...intakeForm, expiry_date: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>WAREHOUSE</label>
                    <input
                      type="text"
                      value={intakeForm.warehouse}
                      onChange={(e) => setIntakeForm({ ...intakeForm, warehouse: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>AISLE</label>
                    <input
                      type="text"
                      value={intakeForm.aisle}
                      onChange={(e) => setIntakeForm({ ...intakeForm, aisle: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>ROW</label>
                    <input
                      type="text"
                      value={intakeForm.row}
                      onChange={(e) => setIntakeForm({ ...intakeForm, row: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>SHELF</label>
                    <input
                      type="text"
                      value={intakeForm.shelf}
                      onChange={(e) => setIntakeForm({ ...intakeForm, shelf: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>BIN (OPTIONAL)</label>
                    <input
                      type="text"
                      value={intakeForm.bin}
                      onChange={(e) => setIntakeForm({ ...intakeForm, bin: e.target.value })}
                    />
                  </div>
                  <div className="form-cell full-span">
                    <button type="submit" className="erp-btn-primary" disabled={loading}>
                      {loading ? 'Recording Inbound...' : 'Commit Inbound Goods to Ledger'}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* [F3] FEFO OUTTAKE & ROUTING */}
            {activeTab === 'outtake' && (
              <div className="panel-inner form-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">FEFO Outtake & Exact Shelf Guidance</h3>
                    <p className="subtext">
                      Queries unexpired batches in strict chronological expiry order and routes pickers to the exact physical shelf.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleOuttakeSubmit} className="erp-form-grid">
                  <div className="form-cell">
                    <label>TARGET PRODUCT SKU</label>
                    <input
                      type="text"
                      value={outtakeForm.sku}
                      onChange={(e) => setOuttakeForm({ ...outtakeForm, sku: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>UNITS REQUIRED</label>
                    <input
                      type="number"
                      min="1"
                      value={outtakeForm.quantity}
                      onChange={(e) => setOuttakeForm({ ...outtakeForm, quantity: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell full-span">
                    <button type="submit" className="erp-btn-primary" disabled={loading}>
                      {loading ? 'Resolving FEFO Routing...' : 'Generate FEFO Pick Directives'}
                    </button>
                  </div>
                </form>

                {outtakeResult && (
                  <div className="erp-result-container">
                    <div className="result-banner-header">
                      <span>FEFO DISPATCH DIRECTIVES GENERATED</span>
                      <span>Total Units Deducted: <strong>{outtakeResult.total_deducted}</strong></span>
                    </div>

                    <div className="pick-cards-stack">
                      {outtakeResult.pick_directions.map((p, idx) => (
                        <div key={idx} className="erp-pick-card">
                          <div className="pick-index">0{idx + 1}</div>
                          <div className="pick-info">
                            <div className="pick-meta-row">
                              <span>Batch ID: <strong>{p.batch_id}</strong></span>
                              <span>Expiry: <strong>{p.expiry_date}</strong></span>
                              <span className="pick-tag">{p.quantity_picked} Units</span>
                            </div>
                            <div className="pick-shelf-instruction">
                              <span className="inst-label">Direct Shelf Routing:</span>
                              <span className="inst-val">{p.shelf_guidance}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* [F4] MANUAL STOCK ADJUSTMENT */}
            {activeTab === 'adjust' && (
              <div className="panel-inner form-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Manual Stock Adjustment (Mandatory Reason Code)</h3>
                    <p className="subtext">
                      Logs stock modifications for influencer samples, warehouse leakage, or audit reconciliation. Reason code is required.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleAdjustSubmit} className="erp-form-grid">
                  <div className="form-cell">
                    <label>PRODUCT SKU</label>
                    <input
                      type="text"
                      value={adjustForm.sku}
                      onChange={(e) => setAdjustForm({ ...adjustForm, sku: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>BATCH NUMBER / ID</label>
                    <input
                      type="text"
                      value={adjustForm.batch_id}
                      placeholder="e.g. BATCH-PURA-26A"
                      onChange={(e) => setAdjustForm({ ...adjustForm, batch_id: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>LOCATION UUID</label>
                    <input
                      type="text"
                      value={adjustForm.location_id}
                      placeholder="Select batch location from overview"
                      onChange={(e) => setAdjustForm({ ...adjustForm, location_id: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>QUANTITY CHANGE (+/-)</label>
                    <input
                      type="number"
                      value={adjustForm.quantity_change}
                      onChange={(e) => setAdjustForm({ ...adjustForm, quantity_change: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell full-span">
                    <label>MANDATORY REASON CODE <span className="req-star">*</span></label>
                    <select
                      value={adjustForm.reason_code}
                      onChange={(e) => setAdjustForm({ ...adjustForm, reason_code: e.target.value })}
                      required
                    >
                      <option value="INFLUENCER_SEEDING">Influencer Seeding / PR Gifting</option>
                      <option value="DAMAGED_IN_TRANSIT">Damaged In Transit / Broken Seal</option>
                      <option value="EXPIRED_DISPOSAL">Quarantined Expired Stock Disposal</option>
                      <option value="AUDIT_RECONCILIATION">Physical Inventory Count Audit</option>
                      <option value="LAB_TESTING_QA">Quality Assurance Mineral Purity Sampling</option>
                    </select>
                  </div>
                  <div className="form-cell full-span">
                    <button type="submit" className="erp-btn-primary" disabled={loading}>
                      {loading ? 'Recording Adjustment...' : 'Commit Manual Stock Adjustment'}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* [F5] BOGO & OMNICHANNEL ORDERS */}
            {activeTab === 'order' && (
              <div className="panel-inner form-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Omnichannel Order Processing & BOGO Decomposition</h3>
                    <p className="subtext">
                      Processes marketplace orders. Promotional BOGO SKUs decompose automatically into base product quantities.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleOrderSubmit} className="erp-form-grid">
                  <div className="form-cell">
                    <label>ORDER REFERENCE ID</label>
                    <input
                      type="text"
                      value={orderForm.order_id}
                      onChange={(e) => setOrderForm({ ...orderForm, order_id: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>ORIGIN MARKETPLACE CHANNEL</label>
                    <select
                      value={orderForm.source}
                      onChange={(e) => setOrderForm({ ...orderForm, source: e.target.value })}
                    >
                      <option value="SHOPIFY">Shopify Online Store</option>
                      <option value="AMAZON">Amazon (SP-API)</option>
                      <option value="FLIPKART">Flipkart Marketplace</option>
                    </select>
                  </div>
                  <div className="form-cell">
                    <label>ORDERED SKU (Try PROMO-BOGO-PURASTONE)</label>
                    <input
                      type="text"
                      value={orderForm.sku}
                      onChange={(e) => setOrderForm({ ...orderForm, sku: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell">
                    <label>ORDERED QUANTITY</label>
                    <input
                      type="number"
                      min="1"
                      value={orderForm.quantity}
                      onChange={(e) => setOrderForm({ ...orderForm, quantity: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-cell full-span">
                    <button type="submit" className="erp-btn-primary" disabled={loading}>
                      {loading ? 'Processing Order...' : 'Execute Order Fulfillment & Rate-Limited Sync'}
                    </button>
                  </div>
                </form>

                {orderResult && (
                  <div className="erp-result-container">
                    <div className="result-banner-header">
                      <span>ORDER DECOMPOSITION & DISPATCH SUMMARY</span>
                      <span>Ref: <strong>{orderResult.order_id}</strong> &bull; Origin: <strong>{orderResult.source}</strong></span>
                    </div>

                    {orderResult.fulfilled_items.map((it, idx) => (
                      <div key={idx} className="erp-bogo-card">
                        <div className="bogo-head">
                          <span className={`bogo-badge ${it.is_bundle ? 'bundle' : ''}`}>
                            {it.is_bundle ? 'PROMOTIONAL BUNDLE' : 'STANDARD SKU'}
                          </span>
                          <h4>{it.ordered_sku}</h4>
                        </div>
                        <p className="bogo-expl">
                          Ordered: <strong>{it.ordered_quantity} unit(s)</strong> &rarr; Decomposed into <strong>{it.actual_quantity_deducted} unit(s)</strong> of base mineral SKU <code>{it.base_sku}</code> (Multiplier: x{it.quantity_multiplier})
                        </p>

                        <div className="bogo-pick-lines">
                          {it.pick_directions.map((p, pIdx) => (
                            <div key={pIdx} className="bogo-pick-item">
                              <span><strong>Batch:</strong> {p.batch_id}</span>
                              <span><strong>Routing:</strong> {p.shelf_guidance}</span>
                              <span className="deduct-qty">Pick: <strong>{p.quantity_picked}</strong> units</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* [F6] IMMUTABLE AUDIT TRAIL */}
            {activeTab === 'logs' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Immutable Transaction Log & Audit Trail</h3>
                    <p className="subtext">
                      Append-only record of every intake, outtake, and adjustment. Database signals forbid updates and deletions.
                    </p>
                  </div>
                  <button className="erp-btn-secondary" onClick={fetchTransactions} disabled={loading}>
                    {loading ? 'Refreshing...' : '↻ Refresh Audit Trail'}
                  </button>
                </div>

                <table className="erp-dense-table">
                  <thead>
                    <tr>
                      <th>TIMESTAMP (UTC)</th>
                      <th>SKU</th>
                      <th>BATCH ID</th>
                      <th>TYPE</th>
                      <th>QTY DELTA</th>
                      <th>SOURCE</th>
                      <th>REASON CODE / NOTES</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((l) => (
                      <tr key={l.id}>
                        <td className="mono-date">{new Date(l.timestamp).toLocaleString()}</td>
                        <td><code className="erp-sku-badge">{l.product_sku}</code></td>
                        <td>{l.batch_id || '—'}</td>
                        <td>
                          <span className={`erp-type-pill ${l.transaction_type.toLowerCase()}`}>
                            {l.transaction_type}
                          </span>
                        </td>
                        <td className={l.quantity_change > 0 ? 'delta-pos' : 'delta-neg'}>
                          {l.quantity_change > 0 ? `+${l.quantity_change}` : l.quantity_change}
                        </td>
                        <td><span className="erp-channel-tag">{l.source}</span></td>
                        <td><span className="erp-reason-notes">{l.reason_code ? l.reason_code : '—'}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* ========================================================
                B2B WHOLESALER HUB SUB-SECTIONS
               ======================================================== */}

            {/* [F8] WHOLESALER EXECUTIVE DASHBOARD */}
            {activeTab === 'ws_dashboard' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">B2B Wholesaler Executive Performance & Profit Yield Dashboard</h3>
                    <p className="subtext">
                      Comprehensive revenue, locked COGS baselines, realized margins, and partner account performance across all legal entities.
                    </p>
                  </div>
                  <button className="erp-btn-secondary" onClick={fetchWholesalerData} disabled={loading}>
                    {loading ? 'Refreshing...' : '↻ Refresh Wholesaler Data'}
                  </button>
                </div>

                {/* Master Wholesale KPI Deck */}
                <section className="erp-metrics-deck" style={{ marginBottom: '22px' }}>
                  <div className="metric-box box-expired">
                    <div className="metric-header">B2B ACTIVE WHOLESALERS</div>
                    <div className="metric-value">
                      {wholesaleAnalytics?.active_wholesalers_count ?? 0} <span className="unit">Approved</span>
                    </div>
                    <div className="metric-sub">
                      {wholesaleAnalytics?.pending_wholesalers_count ?? 0} Pending Admin Review
                    </div>
                  </div>

                  <div className="metric-box box-total">
                    <div className="metric-header">TOTAL WHOLESALE REVENUE</div>
                    <div className="metric-value">₹{wholesaleAnalytics?.total_wholesale_revenue ?? '0.00'}</div>
                    <div className="metric-sub">{wholesaleAnalytics?.total_orders_count ?? 0} Confirmed B2B Orders</div>
                  </div>

                  <div className="metric-box box-sellable">
                    <div className="metric-header">TOTAL REALIZED NET PROFIT</div>
                    <div className="metric-value">₹{wholesaleAnalytics?.total_wholesale_profit ?? '0.00'}</div>
                    <div className="metric-sub">Total COGS: ₹{wholesaleAnalytics?.total_wholesale_cogs ?? '0.00'}</div>
                  </div>

                  <div className="metric-box box-health">
                    <div className="metric-header">SYSTEM PROFIT MARGIN YIELD</div>
                    <div className="metric-value">{wholesaleAnalytics?.system_net_profit_margin_percentage ?? '0.00'}%</div>
                    <div className="metric-sub">Net Realized Margin Efficiency</div>
                  </div>
                </section>

                {/* Per-Wholesaler Performance Table */}
                <div className="erp-card-box">
                  <h4 className="box-title">Individual Wholesaler Margin Yield Rankings</h4>
                  <table className="erp-dense-table">
                    <thead>
                      <tr>
                        <th>WHOLESALER LEGAL ENTITY</th>
                        <th>GSTIN</th>
                        <th>STATUS</th>
                        <th>CONFIRMED ORDERS</th>
                        <th>TOTAL REVENUE</th>
                        <th>NET PROFIT</th>
                        <th>EXACT PROFIT MARGIN YIELD</th>
                        <th>INSPECT DETAILS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wholesaleAnalytics?.wholesalers?.map((w) => (
                        <tr key={w.id}>
                          <td><strong>{w.name}</strong></td>
                          <td><code>{w.gstin}</code></td>
                          <td><span className={`status-pill ${w.status.toLowerCase()}`}>{w.status}</span></td>
                          <td>{w.orders_count}</td>
                          <td>₹{w.revenue}</td>
                          <td><span className="delta-pos">₹{w.net_profit}</span></td>
                          <td>
                            <span className="yield-badge">
                              {w.margin_yield_percentage}% Yield
                            </span>
                          </td>
                          <td>
                            <button
                              className="erp-action-btn"
                              onClick={() => handleViewParentAnalytics(w.id)}
                            >
                              View Deep Yield
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Individual Wholesaler Modal Detail View */}
                {selectedParentAnalytics && (
                  <div className="individual-yield-box">
                    <div className="yield-header">
                      <h5>Wholesaler Deep-Dive: {selectedParentAnalytics.name} ({selectedParentAnalytics.gstin})</h5>
                      <button className="btn-close" onClick={() => setSelectedParentAnalytics(null)}>✕</button>
                    </div>
                    <div className="yield-stats-grid">
                      <div>Total Orders: <strong>{selectedParentAnalytics.total_orders}</strong></div>
                      <div>Total Revenue: <strong>₹{selectedParentAnalytics.total_revenue}</strong></div>
                      <div>Total COGS: <strong>₹{selectedParentAnalytics.total_cogs}</strong></div>
                      <div>Net Profit: <strong className="delta-pos">₹{selectedParentAnalytics.net_profit}</strong></div>
                      <div>Exact Margin Yield: <strong className="yield-text">{selectedParentAnalytics.margin_yield_percentage}%</strong></div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* [F9] CREATE WHOLESALE ORDER (DEDICATED MULTI-PRODUCT PAGE) */}
            {activeTab === 'ws_create_order' && (() => {
              const selectedBranch = wholesalerChildren.find(
                (c) => String(c.id) === String(newOrderForm.child_id)
              );

              // Calculate live order financial totals
              let orderNetTotal = 0;
              let orderGstTotal = 0;
              let orderCogsTotal = 0;

              newOrderForm.items.forEach((item) => {
                const qty = parseFloat(item.quantity) || 0;
                const price = parseFloat(item.unit_price) || 0;
                const gst = parseFloat(item.gst_percentage) || 0;
                const net = qty * price;
                const gstAmt = (net * gst) / 100;
                orderNetTotal += net;
                orderGstTotal += gstAmt;

                const pObj = inventory.find((p) => p.sku === item.sku);
                const cogs = pObj ? parseFloat(pObj.base_cost) || 0 : 0;
                orderCogsTotal += qty * cogs;
              });

              const orderGrandTotal = orderNetTotal + orderGstTotal;
              const orderEstProfit = orderNetTotal - orderCogsTotal;
              const orderEstMarginPct =
                orderNetTotal > 0 ? ((orderEstProfit / orderNetTotal) * 100).toFixed(2) : '0.00';

              return (
                <div className="panel-inner">
                  <div className="panel-top-controls">
                    <div className="section-title-wrap">
                      <h3 className="serif-title">New B2B Wholesale Order Intake & Cost Ledger</h3>
                      <p className="subtext">
                        Select an approved wholesaler branch, add multiple products, and manually input the unit price and GST percentage for each product.
                      </p>
                    </div>
                  </div>

                  <form onSubmit={handleWsOrderSubmit}>
                    {/* Wholesaler Selection */}
                    <div className="erp-card-box" style={{ marginBottom: '18px' }}>
                      <h4 className="box-title">1. Wholesaler Identification & Destination</h4>
                      <div className="form-cell" style={{ maxWidth: '520px', marginBottom: '14px' }}>
                        <label>SELECT ORDERING BRANCH (CHILD ACCOUNT) <span className="req-star">*</span></label>
                        <select
                          value={newOrderForm.child_id}
                          onChange={(e) => {
                            const cId = e.target.value;
                            const branch = wholesalerChildren.find((c) => String(c.id) === String(cId));
                            setNewOrderForm({
                              ...newOrderForm,
                              child_id: cId,
                              po_number: generateAutoPoNumber(branch?.store_id),
                            });
                          }}
                          required
                        >
                          <option value="">-- Choose Approved Branch --</option>
                          {wholesalerChildren.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.branch_name} ({c.store_id}) - {c.parent_name}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Readonly Wholesaler & Branch Details Box */}
                      {selectedBranch ? (
                        <div className="wholesaler-info-badge-box">
                          <div className="badge-col">
                            <span className="badge-lbl">MASTER LEGAL ENTITY</span>
                            <span className="badge-txt">{selectedBranch.parent_name}</span>
                          </div>
                          <div className="badge-col">
                            <span className="badge-lbl">STORE BRANCH & ID</span>
                            <span className="badge-txt">
                              {selectedBranch.branch_name} ({selectedBranch.store_id})
                            </span>
                          </div>
                          <div className="badge-col">
                            <span className="badge-lbl">SHIPPING FREIGHT ADDRESS</span>
                            <span className="badge-txt">{selectedBranch.shipping_address}</span>
                          </div>
                          <div className="badge-col">
                            <span className="badge-lbl">CONTACT PERSON</span>
                            <span className="badge-txt">{selectedBranch.contact_person}</span>
                          </div>
                        </div>
                      ) : (
                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', fontStyle: 'italic' }}>
                          Select a branch to view registered legal entity, GSTIN, and destination address.
                        </div>
                      )}

                      {/* Auto-Generated PO & Delivery Notes */}
                      <div className="erp-form-grid" style={{ gridTemplateColumns: '1fr 2fr', marginTop: '14px' }}>
                        <div className="form-cell">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                            <label style={{ margin: 0 }}>
                              PURCHASE ORDER / REF NO. <span style={{ color: '#0284c7', fontWeight: 700 }}>(AUTO-GENERATED)</span>
                            </label>
                            <button
                              type="button"
                              onClick={() => {
                                const branch = wholesalerChildren.find((c) => String(c.id) === String(newOrderForm.child_id));
                                setNewOrderForm({ ...newOrderForm, po_number: generateAutoPoNumber(branch?.store_id) });
                              }}
                              style={{
                                background: 'transparent',
                                border: 'none',
                                color: 'var(--burnt-clay)',
                                cursor: 'pointer',
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                padding: 0
                              }}
                              title="Generate new PO number"
                            >
                              ↻ Regenerate
                            </button>
                          </div>
                          <input
                            type="text"
                            value={newOrderForm.po_number}
                            readOnly
                            style={{
                              backgroundColor: 'var(--soft-linen-light)',
                              fontWeight: '700',
                              fontFamily: 'monospace',
                              letterSpacing: '0.04em',
                              color: 'var(--burnt-clay-dark)',
                              border: '1px solid var(--soft-linen-border)',
                              cursor: 'default'
                            }}
                          />
                        </div>
                        <div className="form-cell">
                          <label>DISPATCH & FREIGHT INSTRUCTIONS (MANUAL)</label>
                          <input
                            type="text"
                            placeholder="e.g. Express courier transit, fragile alum mineral roll-ons"
                            value={newOrderForm.notes}
                            onChange={(e) =>
                              setNewOrderForm({ ...newOrderForm, notes: e.target.value })
                            }
                          />
                        </div>
                      </div>
                    </div>

                    {/* Multi-Product Line Items Builder */}
                    <div className="erp-card-box" style={{ marginBottom: '18px' }}>
                      <h4 className="box-title">2. Product Selection, Manual Price & GST Line Items</h4>
                      <p className="subtext" style={{ marginBottom: '12px' }}>
                        Select products from the catalog. Enter the amount per piece and GST percentage manually for every item.
                      </p>

                      <div className="order-items-table-wrap">
                        <table className="erp-dense-table order-builder-table">
                          <thead>
                            <tr>
                              <th style={{ width: '40px' }}>#</th>
                              <th style={{ minWidth: '220px' }}>PRODUCT (NAME & SKU)</th>
                              <th style={{ width: '110px' }}>QTY (PCS)</th>
                              <th style={{ width: '130px' }}>AMOUNT / PC (₹)</th>
                              <th style={{ width: '90px' }}>GST %</th>
                              <th style={{ width: '110px' }}>TAXABLE NET</th>
                              <th style={{ width: '110px' }}>GST AMT</th>
                              <th style={{ width: '120px' }}>LINE TOTAL</th>
                              <th style={{ width: '50px' }}></th>
                            </tr>
                          </thead>
                          <tbody>
                            {newOrderForm.items.map((item, idx) => {
                              const qty = parseFloat(item.quantity) || 0;
                              const unitPrice = parseFloat(item.unit_price) || 0;
                              const gstPct = parseFloat(item.gst_percentage) || 0;
                              const lineNet = qty * unitPrice;
                              const lineGst = (lineNet * gstPct) / 100;
                              const lineTotal = lineNet + lineGst;

                              return (
                                <tr key={idx}>
                                  <td className="item-num">{idx + 1}</td>
                                  <td>
                                    <select
                                      value={item.sku}
                                      onChange={(e) => {
                                        const selectedSku = e.target.value;
                                        const matchedProd = inventory.find((p) => p.sku === selectedSku);
                                        const updatedItems = [...newOrderForm.items];
                                        updatedItems[idx] = {
                                          ...updatedItems[idx],
                                          sku: selectedSku,
                                          unit_price: matchedProd ? matchedProd.default_b2b_price : updatedItems[idx].unit_price,
                                        };
                                        setNewOrderForm({ ...newOrderForm, items: updatedItems });
                                      }}
                                      className="item-prod-select"
                                    >
                                      {inventory.map((p) => (
                                        <option key={p.sku} value={p.sku}>
                                          {p.product_name} ({p.sku})
                                        </option>
                                      ))}
                                    </select>
                                  </td>
                                  <td>
                                    <input
                                      type="number"
                                      min="1"
                                      value={item.quantity}
                                      onChange={(e) => {
                                        const updatedItems = [...newOrderForm.items];
                                        updatedItems[idx].quantity = e.target.value;
                                        setNewOrderForm({ ...newOrderForm, items: updatedItems });
                                      }}
                                      className="item-input-num"
                                      required
                                    />
                                  </td>
                                  <td>
                                    <input
                                      type="number"
                                      step="0.01"
                                      min="0"
                                      value={item.unit_price}
                                      onChange={(e) => {
                                        const updatedItems = [...newOrderForm.items];
                                        updatedItems[idx].unit_price = e.target.value;
                                        setNewOrderForm({ ...newOrderForm, items: updatedItems });
                                      }}
                                      className="item-input-num"
                                      required
                                    />
                                  </td>
                                  <td>
                                    <input
                                      type="number"
                                      step="0.1"
                                      min="0"
                                      value={item.gst_percentage}
                                      onChange={(e) => {
                                        const updatedItems = [...newOrderForm.items];
                                        updatedItems[idx].gst_percentage = e.target.value;
                                        setNewOrderForm({ ...newOrderForm, items: updatedItems });
                                      }}
                                      className="item-input-num"
                                      required
                                    />
                                  </td>
                                  <td>₹{lineNet.toFixed(2)}</td>
                                  <td>₹{lineGst.toFixed(2)}</td>
                                  <td><strong>₹{lineTotal.toFixed(2)}</strong></td>
                                  <td>
                                    {newOrderForm.items.length > 1 && (
                                      <button
                                        type="button"
                                        className="btn-remove-item"
                                        onClick={() => {
                                          const updatedItems = newOrderForm.items.filter((_, i) => i !== idx);
                                          setNewOrderForm({ ...newOrderForm, items: updatedItems });
                                        }}
                                        title="Remove item"
                                      >
                                        ✕
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>

                        <div className="table-bottom-actions">
                          <button
                            type="button"
                            className="erp-btn-secondary"
                            onClick={() => {
                              const defaultSku = inventory.length > 0 ? inventory[0].sku : 'PURA-ALUM-ROLLON-100';
                              const defaultPrice = inventory.length > 0 ? inventory[0].default_b2b_price : 450;
                              setNewOrderForm({
                                ...newOrderForm,
                                items: [
                                  ...newOrderForm.items,
                                  {
                                    sku: defaultSku,
                                    quantity: 1,
                                    unit_price: defaultPrice,
                                    gst_percentage: 18.0,
                                  },
                                ],
                              });
                            }}
                          >
                            + Add Another Product Item
                          </button>
                        </div>
                      </div>

                      {/* Live Calculated Order Summary Deck */}
                      <div className="order-summary-deck">
                        <div className="summary-col">
                          <span className="sum-label">TAXABLE SUBTOTAL</span>
                          <span className="sum-val">₹{orderNetTotal.toFixed(2)}</span>
                        </div>
                        <div className="summary-col">
                          <span className="sum-label">TOTAL GST PAYABLE</span>
                          <span className="sum-val">₹{orderGstTotal.toFixed(2)}</span>
                        </div>
                        <div className="summary-col">
                          <span className="sum-label">TOTAL BASE COGS</span>
                          <span className="sum-val">₹{orderCogsTotal.toFixed(2)}</span>
                        </div>
                        <div className="summary-col">
                          <span className="sum-label">PROJECTED PROFIT</span>
                          <span className="sum-val delta-pos">
                            ₹{orderEstProfit.toFixed(2)} ({orderEstMarginPct}%)
                          </span>
                        </div>
                        <div className="summary-col">
                          <span className="sum-label">GRAND TOTAL PAYABLE</span>
                          <span className="sum-val grand-total-val">₹{orderGrandTotal.toFixed(2)}</span>
                        </div>
                      </div>

                      <button
                        type="submit"
                        className="erp-btn-primary"
                        disabled={loading}
                        style={{ padding: '12px 24px', fontSize: '0.92rem' }}
                      >
                        {loading ? 'Submitting Order...' : 'Lock In Multi-Item Wholesale Order'}
                      </button>
                    </div>
                  </form>
                </div>
              );
            })()}

            {/* [F10] B2B ORDERS & DISCOUNT DESK */}
            {activeTab === 'ws_orders' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Wholesale Order Management, Discounts & FEFO Outtake</h3>
                    <p className="subtext">
                      Manage orders, apply margin-guarded discounts, and trigger FEFO inventory allocation with automatic PDF invoice generation.
                    </p>
                  </div>
                  <button className="erp-btn-primary" onClick={() => setActiveTab('ws_create_order')}>
                    + Create New Wholesale Order [F9]
                  </button>
                </div>

                {/* Admin Discount Engine Panel */}
                <div className="erp-card-box" style={{ marginBottom: '20px' }}>
                  <h4 className="box-title">Admin Custom Discount Engine (Absolute Margin Floor Guard)</h4>
                  <p className="subtext" style={{ marginBottom: '14px' }}>
                    Calculates the absolute COGS floor across all order line items and strictly prevents discounts that would produce negative margins.
                  </p>
                  <form onSubmit={handleApplyDiscount} className="erp-form-vertical" style={{ maxWidth: '820px' }}>
                    <div className="form-cell">
                      <label>SELECT DRAFT WHOLESALE ORDER</label>
                      <select
                        value={discountForm.order_id}
                        onChange={(e) => setDiscountForm({ ...discountForm, order_id: e.target.value })}
                        required
                      >
                        <option value="">-- Choose Order to Discount --</option>
                        {wholesaleOrders
                          .filter((o) => ['DRAFT', 'DISCOUNT_APPLIED'].includes(o.status))
                          .map((o) => (
                            <option key={o.id} value={o.id}>
                              Ref: {o.id.substring(0, 8)} | {o.branch_name} ({o.parent_name}) | Subtotal: ₹{o.subtotal} | COGS Floor: ₹{o.total_cogs}
                            </option>
                          ))}
                      </select>
                    </div>
                    <div className="erp-form-grid" style={{ gridTemplateColumns: '1fr 1fr 1fr', alignItems: 'flex-end' }}>
                      <div className="form-cell">
                        <label>DISCOUNT TYPE</label>
                        <select
                          value={discountForm.discount_type}
                          onChange={(e) => setDiscountForm({ ...discountForm, discount_type: e.target.value })}
                        >
                          <option value="PERCENTAGE">Percentage (%)</option>
                          <option value="FLAT">Flat Cash Discount (₹)</option>
                        </select>
                      </div>
                      <div className="form-cell">
                        <label>DISCOUNT VALUE</label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={discountForm.discount_value}
                          onChange={(e) => setDiscountForm({ ...discountForm, discount_value: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <button
                          type="submit"
                          className="erp-btn-discount"
                          disabled={loading}
                          style={{ width: '100%', height: '38px', marginTop: 0 }}
                        >
                          Apply & Enforce Margin Floor
                        </button>
                      </div>
                    </div>
                  </form>
                </div>

                {/* Active Wholesale Orders Table */}
                <div className="erp-card-box">
                  <h4 className="box-title">Active Wholesale Orders & FEFO Fulfillment Status</h4>
                  <div className="orders-scroll-table">
                    <table className="erp-dense-table">
                      <thead>
                        <tr>
                          <th>ORDER REF / PO</th>
                          <th>BRANCH / LEGAL PARENT</th>
                          <th>ITEMS</th>
                          <th>TAXABLE SUBTOTAL</th>
                          <th>DISCOUNT</th>
                          <th>NET VALUE</th>
                          <th>TOTAL GST</th>
                          <th>GRAND TOTAL</th>
                          <th>NET PROFIT</th>
                          <th>STATUS</th>
                          <th>ACTION</th>
                        </tr>
                      </thead>
                      <tbody>
                        {wholesaleOrders.map((o) => (
                          <tr key={o.id}>
                            <td>
                              <code className="mono-date">{o.id.substring(0, 8)}...</code>
                              {o.po_number && (
                                <div style={{ fontSize: '0.72rem', color: 'var(--burnt-clay)' }}>
                                  PO: {o.po_number}
                                </div>
                              )}
                            </td>
                            <td>
                              <strong>{o.branch_name}</strong><br />
                              <small style={{ color: 'var(--text-secondary)' }}>{o.parent_name}</small>
                            </td>
                            <td>
                              <span className="erp-channel-tag">{o.items ? o.items.length : 1} Product(s)</span>
                            </td>
                            <td>₹{o.subtotal}</td>
                            <td><span className="delta-neg">-₹{o.discount_amount}</span></td>
                            <td><strong>₹{o.final_value}</strong></td>
                            <td>₹{o.total_gst || '0.00'}</td>
                            <td><strong style={{ color: 'var(--burnt-clay)' }}>₹{o.grand_total || o.final_value}</strong></td>
                            <td><span className="delta-pos">₹{o.net_profit}</span></td>
                            <td>
                              <span className={`order-status-pill ${o.status.toLowerCase()}`}>
                                {o.status}
                              </span>
                            </td>
                            <td>
                              {['DRAFT', 'DISCOUNT_APPLIED'].includes(o.status) ? (
                                <button
                                  className="erp-btn-confirm"
                                  onClick={() => handleConfirmOrder(o.id)}
                                  disabled={loading}
                                >
                                  Confirm & FEFO Deduct
                                </button>
                              ) : (
                                <span className="status-fulfilled">Fulfilled</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* [F11] MASTER ONBOARDING & APPROVAL */}
            {activeTab === 'ws_onboard' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Wholesaler Master Onboarding & Legal Entity Review</h3>
                    <p className="subtext">
                      Captures business legal identity (GSTIN / Trade License). Pending entities require Admin approval before branch creation.
                    </p>
                  </div>
                </div>

                <div className="erp-two-column-split">
                  {/* Onboarding Form */}
                  <div className="erp-card-box">
                    <h4 className="box-title">New Wholesaler Registration</h4>
                    <form onSubmit={handleOnboardSubmit} className="erp-form-vertical">
                      <div className="form-cell">
                        <label>LEGAL BUSINESS NAME</label>
                        <input
                          type="text"
                          placeholder="e.g. Aura Wellness Retail Pvt Ltd"
                          value={onboardForm.name}
                          onChange={(e) => setOnboardForm({ ...onboardForm, name: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <label>GSTIN / TRADE LICENSE ID</label>
                        <input
                          type="text"
                          placeholder="e.g. 27AABCA1234F1Z5"
                          value={onboardForm.gstin}
                          onChange={(e) => setOnboardForm({ ...onboardForm, gstin: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <label>MASTER CORPORATE EMAIL</label>
                        <input
                          type="email"
                          placeholder="e.g. procurement@aurawellness.com"
                          value={onboardForm.master_email}
                          onChange={(e) => setOnboardForm({ ...onboardForm, master_email: e.target.value })}
                          required
                        />
                      </div>
                      <button type="submit" className="erp-btn-primary" disabled={loading}>
                        {loading ? 'Submitting...' : 'Register Master Wholesaler'}
                      </button>
                    </form>
                  </div>

                  {/* Registered Wholesalers List & Approval */}
                  <div className="erp-card-box">
                    <h4 className="box-title">Master Wholesaler Verification Queue</h4>
                    <div className="wholesaler-list-scroll">
                      {wholesalerParents.map((wp) => (
                        <div key={wp.id} className="wholesaler-item-card">
                          <div className="item-meta-top">
                            <span className="item-name">{wp.name}</span>
                            <span className={`status-pill ${wp.status.toLowerCase()}`}>{wp.status}</span>
                          </div>
                          <div className="item-details">
                            <span>GSTIN: <strong>{wp.gstin}</strong></span>
                            <span>Email: {wp.master_email}</span>
                            <span>Registered Branches: <strong>{wp.branches_count}</strong></span>
                          </div>
                          {wp.status === 'PENDING' && (
                            <button
                              className="erp-btn-approve"
                              onClick={() => handleApproveParent(wp.id)}
                              disabled={loading}
                            >
                              ✓ Approve Wholesaler
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* [F12] BRANCH & CHILD ID PORTAL */}
            {activeTab === 'ws_children' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Branch & Agent Login ID Generation Portal</h3>
                    <p className="subtext">
                      Self-serve portal for approved Master Wholesalers to generate and manage distinct login IDs for physical stores and branches.
                    </p>
                  </div>
                </div>

                <div className="erp-two-column-split">
                  {/* Create Branch Form */}
                  <div className="erp-card-box">
                    <h4 className="box-title">Generate Child Store Login ID</h4>
                    <form onSubmit={handleChildSubmit} className="erp-form-vertical">
                      <div className="form-cell">
                        <label>SELECT APPROVED MASTER WHOLESALER</label>
                        <select
                          value={childForm.parent_id}
                          onChange={(e) => setChildForm({ ...childForm, parent_id: e.target.value })}
                          required
                        >
                          <option value="">-- Choose Approved Master --</option>
                          {wholesalerParents
                            .filter((p) => p.status === 'APPROVED')
                            .map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name} ({p.gstin})
                              </option>
                            ))}
                        </select>
                      </div>
                      <div className="form-cell">
                        <label>BRANCH / STORE NAME</label>
                        <input
                          type="text"
                          placeholder="e.g. Bandra West Flagship Store"
                          value={childForm.branch_name}
                          onChange={(e) => setChildForm({ ...childForm, branch_name: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <label>STORE UNIQUE ID</label>
                        <input
                          type="text"
                          placeholder="e.g. AURA-MUM-01"
                          value={childForm.store_id}
                          onChange={(e) => setChildForm({ ...childForm, store_id: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <label>LOGIN USERNAME</label>
                        <input
                          type="text"
                          placeholder="e.g. aura_bandra"
                          value={childForm.username}
                          onChange={(e) => setChildForm({ ...childForm, username: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <label>CONTACT PERSON</label>
                        <input
                          type="text"
                          placeholder="e.g. Rajesh Sharma"
                          value={childForm.contact_person}
                          onChange={(e) => setChildForm({ ...childForm, contact_person: e.target.value })}
                          required
                        />
                      </div>
                      <div className="form-cell">
                        <label>SHIPPING DELIVERY ADDRESS</label>
                        <textarea
                          rows="2"
                          placeholder="Exact delivery address for wholesale freight"
                          value={childForm.shipping_address}
                          onChange={(e) => setChildForm({ ...childForm, shipping_address: e.target.value })}
                          required
                        />
                      </div>
                      <button type="submit" className="erp-btn-primary" disabled={loading}>
                        {loading ? 'Spawning Child...' : 'Spawn & Authorize Branch Login ID'}
                      </button>
                    </form>
                  </div>

                  {/* Registered Branches Table */}
                  <div className="erp-card-box">
                    <h4 className="box-title">Active Wholesaler Branches & Agents</h4>
                    <table className="erp-dense-table">
                      <thead>
                        <tr>
                          <th>STORE ID</th>
                          <th>BRANCH NAME</th>
                          <th>PARENT ENTITY</th>
                          <th>LOGIN USER</th>
                          <th>CONTACT</th>
                        </tr>
                      </thead>
                      <tbody>
                        {wholesalerChildren.map((c) => (
                          <tr key={c.id}>
                            <td><code>{c.store_id}</code></td>
                            <td><strong>{c.branch_name}</strong></td>
                            <td>{c.parent_name}</td>
                            <td><span className="mono-date">{c.username}</span></td>
                            <td>{c.contact_person}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* [F13] B2B INVOICES & PDFS */}
            {activeTab === 'ws_invoices' && (
              <div className="panel-inner">
                <div className="panel-top-controls">
                  <div className="section-title-wrap">
                    <h3 className="serif-title">Automated B2B Wholesale Tax Invoices (PDF Archive)</h3>
                    <p className="subtext">
                      Asynchronously generated via Celery upon order confirmation. Includes custom discount line items and parent/child billing data.
                    </p>
                  </div>
                </div>

                <table className="erp-dense-table">
                  <thead>
                    <tr>
                      <th>ORDER REF</th>
                      <th>PARENT LEGAL ENTITY</th>
                      <th>STORE BRANCH</th>
                      <th>TAXABLE VALUE</th>
                      <th>TOTAL GST</th>
                      <th>GRAND TOTAL</th>
                      <th>GENERATION DATE</th>
                      <th>PDF INVOICE DOWNLOAD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wholesaleOrders
                      .filter((o) => o.invoice)
                      .map((o) => (
                        <tr key={o.id}>
                          <td><code className="mono-date">{o.id.substring(0, 8)}...</code></td>
                          <td><strong>{o.parent_name}</strong></td>
                          <td>{o.branch_name} ({o.store_id})</td>
                          <td>₹{o.final_value}</td>
                          <td>₹{o.total_gst || '0.00'}</td>
                          <td><strong>₹{o.grand_total || o.final_value}</strong></td>
                          <td>{new Date(o.invoice.created_at).toLocaleString()}</td>
                          <td>
                            <a
                              href={`http://127.0.0.1:8000${o.invoice.pdf_url}`}
                              target="_blank"
                              rel="noreferrer"
                              className="erp-invoice-link"
                            >
                              📄 Download PDF Invoice
                            </a>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
