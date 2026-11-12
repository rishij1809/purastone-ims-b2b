import React, { useState, useEffect, useCallback } from 'react';

const fmtINR = (val) => {
  const num = Number(val || 0);
  return '₹' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const LOSS_CATEGORIES = [
  { value: 'MANUAL_WAREHOUSE_LOSS', label: 'Warehouse Spillage / Theft / Other' },
  { value: 'QC_LAB_REJECTION', label: 'QC Rejection / R&D Formulation Wastage' },
  { value: 'FEFO_BATCH_EXPIRY', label: 'Expired Skincare Formulation Batch' },
  { value: 'TRANSIT_LR_BREAKAGE', label: 'B2B LR Transit Leakage / Glass Breakage' },
  { value: 'UNRETURNED_RTO_LOSS', label: 'Marketplace Damaged / Lost RTO' },
  { value: 'TESTER_PROMO_BURN', label: 'Complimentary B2B Testers & PR Seeding' },
  { value: 'BAD_DEBT_WRITEOFF', label: 'Defaulted B2B Retailer Receivable' },
  { value: 'MARKETPLACE_SLA_PENALTY', label: 'Marketplace SLA / Chargeback Penalty' },
];

const EXPENSE_BUCKETS = [
  { value: 'META_GOOGLE_ADS', label: 'Meta & Google Performance Ads (CM3)' },
  { value: 'MARKETPLACE_ADS', label: 'Amazon & Flipkart Sponsored Ads (CM3)' },
  { value: 'SALES_COMMISSIONS', label: 'B2B Sales Team Commissions (CM3)' },
  { value: 'INFLUENCER_PR', label: 'Influencer Retainers & PR Campaigns (CM3)' },
  { value: 'PAYROLL_SALARIES', label: 'Company Payroll & Salaries (OPEX)' },
  { value: 'WAREHOUSE_OFFICE_RENT', label: 'Warehouse & Office Rent (OPEX)' },
  { value: 'SAAS_CLOUD_INFRA', label: 'Cloud, ERP & Software Subscriptions (OPEX)' },
  { value: 'LEGAL_ADMIN_UTILITIES', label: 'Legal, CA, Lab Testing & Utilities (OPEX)' },
];

const CHANNELS = [
  { value: '', label: 'Shared Company-Wide (Auto Prorate)' },
  { value: 'B2B_WHOLESALE', label: 'B2B Wholesaler ERP' },
  { value: 'SHOPIFY_D2C', label: 'Shopify D2C' },
  { value: 'AMAZON', label: 'Amazon India' },
  { value: 'FLIPKART', label: 'Flipkart' },
  { value: 'MANUAL_OFFLINE', label: 'Manual / Offline Retail' },
];

function DeltaBadge({ pct }) {
  const n = Number(pct || 0);
  const up = n >= 0;
  return (
    <span className={`fin-delta-badge ${up ? 'up' : 'down'}`}>
      {up ? '▲' : '▼'} {Math.abs(n).toFixed(1)}% vs prior
    </span>
  );
}

function WaterfallChart({ bridge }) {
  if (!bridge || bridge.length === 0) return null;
  const maxAbs = Math.max(...bridge.map((b) => Math.abs(b.amount)), 1);

  return (
    <div className="fin-waterfall-wrap">
      {bridge.map((step, i) => {
        const pct = Math.min(100, Math.max(4, (Math.abs(step.amount) / maxAbs) * 100));
        const isNeg = step.amount < 0;
        const barClass =
          step.type === 'deduction'
            ? 'bar-deduction'
            : step.type === 'final'
            ? step.amount >= 0
              ? 'bar-final-pos'
              : 'bar-final-neg'
            : step.type === 'subtotal'
            ? 'bar-subtotal'
            : 'bar-positive';

        return (
          <div key={i} className={`fin-wf-row ${step.type === 'subtotal' || step.type === 'final' ? 'is-total-row' : ''}`}>
            <div className="fin-wf-label">{step.step}</div>
            <div className="fin-wf-track">
              <div className={`fin-wf-bar ${barClass}`} style={{ width: `${pct}%` }} title={`${step.step}: ${fmtINR(step.amount)}`} />
            </div>
            <div className={`fin-wf-val ${isNeg ? 'val-neg' : 'val-pos'}`}>
              {isNeg ? '-' : ''}
              {fmtINR(Math.abs(step.amount))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ScatterHeroChart({ skuRankings }) {
  if (!skuRankings || skuRankings.length === 0) {
    return <p className="erp-muted">No SKU unit economics recorded in this period.</p>;
  }
  const maxRev = Math.max(...skuRankings.map((s) => s.net_revenue), 1000);
  const minMargin = Math.min(...skuRankings.map((s) => s.cm2_pct), -20);
  const maxMargin = Math.max(...skuRankings.map((s) => s.cm2_pct), 60);
  const spanM = Math.max(10, maxMargin - minMargin);

  return (
    <div className="fin-scatter-box">
      <svg viewBox="0 0 560 220" className="fin-scatter-svg">
        <line x1="50" y1="20" x2="50" y2="185" stroke="#d8c7b5" strokeWidth="1.5" />
        <line x1="50" y1="185" x2="540" y2="185" stroke="#d8c7b5" strokeWidth="1.5" />
        {/* Zero CM2% reference line */}
        {minMargin < 0 && maxMargin > 0 && (
          <line
            x1="50"
            x2="540"
            y1={185 - ((0 - minMargin) / spanM) * 155}
            y2={185 - ((0 - minMargin) / spanM) * 155}
            stroke="#a43224"
            strokeDasharray="4 4"
            strokeWidth="1"
          />
        )}
        <text x="295" y="210" textAnchor="middle" fontSize="10" fill="#6e5849">
          Net Revenue (INR) →
        </text>
        <text x="16" y="105" textAnchor="middle" fontSize="10" fill="#6e5849" transform="rotate(-90 16 105)">
          CM2 Margin %
        </text>
        {skuRankings.map((s, idx) => {
          const cx = 65 + (s.net_revenue / maxRev) * 450;
          const cy = 180 - ((s.cm2_pct - minMargin) / spanM) * 150;
          const color =
            s.classification === 'HERO_SKU'
              ? '#246a48'
              : s.classification === 'MARGIN_BLEEDER'
              ? '#a43224'
              : '#a05a3a';
          return (
            <g key={s.sku}>
              <circle cx={cx} cy={cy} r={8} fill={color} fillOpacity="0.82" stroke="#23160e" strokeWidth="1" />
              <text x={cx} y={cy - 11 - (idx % 2) * 8} textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#23160e">
                {s.sku.replace('PURA-', '')} ({s.cm2_pct}%)
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function FinanceCommandCenter({
  activeTab,
  apiBase,
  erpRole,
  inventory,
  notify,
  onRefreshInventory,
}) {
  const [preset, setPreset] = useState('MTD');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [loading, setLoading] = useState(false);

  // Data States
  const [cmdData, setCmdData] = useState(null);
  const [unitData, setUnitData] = useState(null);
  const [reconData, setReconData] = useState(null);
  const [reconChannel, setReconChannel] = useState('ALL');
  const [reconStatus, setReconStatus] = useState('ALL');
  const [lossData, setLossData] = useState(null);
  const [manualSales, setManualSales] = useState([]);
  const [opexEntries, setOpexEntries] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [wcData, setWcData] = useState(null);
  const [lrs, setLrs] = useState([]);

  // Forms
  const [saleForm, setSaleForm] = useState({
    sale_date: new Date().toISOString().slice(0, 10),
    reference_number: '',
    customer_or_store_name: '',
    sku: '',
    quantity: 1,
    gross_amount: '',
    gst_amount: '',
    discount_amount: '0.00',
    manual_cogs_amount: '0.00',
    manual_freight_and_packing: '0.00',
    notes: '',
  });
  const [opexForm, setOpexForm] = useState({
    period_start_date: new Date().toISOString().slice(0, 10),
    period_end_date: new Date().toISOString().slice(0, 10),
    bucket: 'META_GOOGLE_ADS',
    target_channel: 'SHOPIFY_D2C',
    amount_exclusive_gst: '',
    gst_input_credit: '0.00',
    vendor_or_platform_name: '',
    is_paid: true,
  });
  const [lossForm, setLossForm] = useState({
    incurred_date: new Date().toISOString().slice(0, 10),
    category: 'MANUAL_WAREHOUSE_LOSS',
    channel: 'B2B_WHOLESALE',
    affected_batch: '',
    units_lost: 1,
    total_loss_amount: '',
    reason_notes: '',
  });
  const [csvType, setCsvType] = useState('opex');
  const [csvContent, setCsvContent] = useState('');
  const [reconcileModal, setReconcileModal] = useState(null);
  const [settleForm, setSettleForm] = useState({
    actual_settled_payout: '',
    settlement_utr: '',
    platform_commission_fees: '',
    payment_gateway_fees: '',
    outbound_freight_cost: '',
  });
  const [bankInput, setBankInput] = useState('');

  const buildQuery = useCallback(() => {
    if (preset === 'CUSTOM' && customStart && customEnd) {
      return `preset=CUSTOM&start_date=${customStart}&end_date=${customEnd}`;
    }
    return `preset=${preset}`;
  }, [preset, customStart, customEnd]);

  const roleHeaders = useCallback(
    () => ({ 'Content-Type': 'application/json', 'X-ERP-Role': erpRole }),
    [erpRole]
  );

  const loadTabData = useCallback(async () => {
    const q = buildQuery();
    setLoading(true);
    try {
      if (activeTab === 'fin_ceo') {
        const res = await fetch(`${apiBase}/finance/command-center/?${q}`);
        if (res.ok) setCmdData(await res.json());
      } else if (activeTab === 'fin_unit') {
        const res = await fetch(`${apiBase}/finance/unit-economics/?${q}`);
        if (res.ok) setUnitData(await res.json());
      } else if (activeTab === 'fin_reconcile') {
        const res = await fetch(
          `${apiBase}/finance/reconciler/?${q}&channel=${reconChannel}&status=${reconStatus}`
        );
        if (res.ok) setReconData(await res.json());
      } else if (activeTab === 'fin_losses') {
        const res = await fetch(`${apiBase}/finance/losses/?${q}`);
        if (res.ok) setLossData(await res.json());
      } else if (activeTab === 'fin_manual') {
        const [sRes, oRes, lRes, aRes] = await Promise.all([
          fetch(`${apiBase}/finance/manual-sales/`),
          fetch(`${apiBase}/finance/opex/`),
          fetch(`${apiBase}/finance/losses/?${q}`),
          fetch(`${apiBase}/finance/audit-logs/`),
        ]);
        if (sRes.ok) setManualSales(await sRes.json());
        if (oRes.ok) setOpexEntries(await oRes.json());
        if (lRes.ok) setLossData(await lRes.json());
        if (aRes.ok) setAuditLogs(await aRes.json());
      } else if (activeTab === 'fin_cashflow') {
        const [wRes, lrRes] = await Promise.all([
          fetch(`${apiBase}/finance/working-capital/?${q}`),
          fetch(`${apiBase}/finance/lorry-receipts/`),
        ]);
        if (wRes.ok) {
          const d = await wRes.json();
          setWcData(d);
          setBankInput(d.treasury?.cash_in_bank_balance || '');
        }
        if (lrRes.ok) setLrs(await lrRes.json());
      }
    } catch (err) {
      notify(`Failed loading finance data: ${err.message}`, true);
    } finally {
      setLoading(false);
    }
  }, [activeTab, apiBase, buildQuery, reconChannel, reconStatus, notify]);

  useEffect(() => {
    loadTabData();
  }, [loadTabData]);

  const handleRefreshViews = async () => {
    const res = await fetch(`${apiBase}/finance/refresh-views/`, { method: 'POST' });
    if (res.ok) {
      notify('Materialized Views & Redis/Cache snapshot refreshed concurrently.');
      loadTabData();
    }
  };

  const handleCreateManualSale = async (e) => {
    e.preventDefault();
    const payload = { ...saleForm, quantity: Number(saleForm.quantity || 0) };
    if (!payload.sku) delete payload.sku;
    const res = await fetch(`${apiBase}/finance/manual-sales/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify(payload),
    });
    const d = await res.json();
    if (res.ok) {
      notify(`Offline Sale ${d.reference_number} submitted for Admin Maker-Checker Approval.`);
      setSaleForm({ ...saleForm, reference_number: '', customer_or_store_name: '', gross_amount: '', gst_amount: '' });
      loadTabData();
    } else {
      notify(d.error || JSON.stringify(d), true);
    }
  };

  const handleCreateOpex = async (e) => {
    e.preventDefault();
    const payload = { ...opexForm, target_channel: opexForm.target_channel || null };
    const res = await fetch(`${apiBase}/finance/opex/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify(payload),
    });
    const d = await res.json();
    if (res.ok) {
      notify(`Marketing/OPEX entry (${d.vendor_or_platform_name}) queued for Maker-Checker Approval.`);
      setOpexForm({ ...opexForm, amount_exclusive_gst: '', vendor_or_platform_name: '' });
      loadTabData();
    } else {
      notify(d.error || JSON.stringify(d), true);
    }
  };

  const handleCreateLoss = async (e) => {
    e.preventDefault();
    const payload = { ...lossForm, affected_batch: lossForm.affected_batch || null };
    const res = await fetch(`${apiBase}/finance/losses/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify(payload),
    });
    const d = await res.json();
    if (res.ok) {
      notify(`Loss/Leakage record queued for Maker-Checker Approval.`);
      setLossForm({ ...lossForm, total_loss_amount: '', reason_notes: '' });
      loadTabData();
    } else {
      notify(d.error || JSON.stringify(d), true);
    }
  };

  const handleCsvImport = async (e) => {
    e.preventDefault();
    const res = await fetch(`${apiBase}/finance/import-csv/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify({ type: csvType, csv_content: csvContent }),
    });
    const d = await res.json();
    if (res.ok) {
      notify(`Imported ${d.count} CSV rows into PENDING Maker-Checker approval queue.`);
      setCsvContent('');
      loadTabData();
    } else {
      notify(d.error || 'CSV Import failed', true);
    }
  };

  const handleMakerChecker = async (entityType, id, action) => {
    const res = await fetch(`${apiBase}/finance/approvals/${entityType}/${id}/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify({ action }),
    });
    const d = await res.json();
    if (res.ok) {
      notify(`Entry ${action}ED successfully & immutable AuditLog captured.`);
      loadTabData();
      if (onRefreshInventory) onRefreshInventory();
    } else {
      notify(d.error || 'Approval rejected', true);
    }
  };

  const handleReconcileSubmit = async (e) => {
    e.preventDefault();
    const res = await fetch(`${apiBase}/finance/reconciler/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify({
        channel: reconcileModal.channel,
        external_order_ref: reconcileModal.external_order_ref,
        ...settleForm,
      }),
    });
    const d = await res.json();
    if (res.ok) {
      notify(`Order ${d.external_order_ref} transitioned to ${d.reconciliation_status}.`);
      setReconcileModal(null);
      loadTabData();
    } else {
      notify(d.error || 'Reconciliation error', true);
    }
  };

  const handleTreasurySave = async (e) => {
    e.preventDefault();
    const res = await fetch(`${apiBase}/finance/working-capital/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify({ action: 'UPDATE_TREASURY', cash_in_bank_balance: bankInput }),
    });
    if (res.ok) {
      notify('Bank Cash Balance updated & Runway recalculated.');
      loadTabData();
    }
  };

  const handleCollectAR = async (orderRef, amt) => {
    const res = await fetch(`${apiBase}/finance/working-capital/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify({ action: 'COLLECT_B2B_AR', order_ref: orderRef, amount: amt }),
    });
    if (res.ok) {
      notify(`Recorded full B2B collection for ${orderRef}.`);
      loadTabData();
    }
  };

  const handleVerifyPod = async (lrId) => {
    const res = await fetch(`${apiBase}/finance/lorry-receipts/${lrId}/verify-pod/`, {
      method: 'POST',
      headers: roleHeaders(),
      body: JSON.stringify({ pod_status: 'CLEAN', mark_ap_paid: true }),
    });
    if (res.ok) {
      notify('LorryReceipt POD verified & Transporter AP marked Paid.');
      loadTabData();
    }
  };

  const qStr = buildQuery();

  return (
    <div className="fin-command-shell">
      {/* Shared Finance Filter & Export Toolbar */}
      <div className="erp-panel fin-toolbar">
        <div className="fin-preset-pills">
          {['TODAY', '7D', 'MTD', 'QTD', 'YTD', 'ALL', 'CUSTOM'].map((p) => (
            <button
              key={p}
              className={`fin-pill-btn ${preset === p ? 'active' : ''}`}
              onClick={() => setPreset(p)}
            >
              {p}
            </button>
          ))}
          {preset === 'CUSTOM' && (
            <div className="fin-custom-dates">
              <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
              <span>to</span>
              <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
            </div>
          )}
        </div>

        <div className="fin-export-actions">
          <button className="erp-btn-secondary" onClick={handleRefreshViews} disabled={loading}>
            ↻ Refresh MV Cache
          </button>
          <a className="erp-btn-primary fin-dl-btn" href={`${apiBase}/finance/export/pdf/?${qStr}`} target="_blank" rel="noreferrer">
            Boardroom PDF P&amp;L
          </a>
          <a className="erp-btn-secondary fin-dl-btn" href={`${apiBase}/finance/export/xlsx/?${qStr}`} target="_blank" rel="noreferrer">
            CA Excel (.xlsx)
          </a>
          <a className="erp-btn-secondary fin-dl-btn" href={`${apiBase}/finance/export/csv/?${qStr}`} target="_blank" rel="noreferrer">
            CA CSV
          </a>
        </div>
      </div>

      {/* VIEW 0: MASTER CEO COMMAND CENTER */}
      {activeTab === 'fin_ceo' && cmdData && (
        <div className="erp-view-stack">
          <div className="fin-kpi-ribbon">
            <div className="erp-kpi-card fin-kpi">
              <span className="kpi-label">GROSS SALES (GMV)</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.gmv)}</span>
              <DeltaBadge pct={cmdData.deltas.gmv_pct} />
            </div>
            <div className="erp-kpi-card fin-kpi">
              <span className="kpi-label">NET REVENUE</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.net_revenue)}</span>
              <DeltaBadge pct={cmdData.deltas.net_revenue_pct} />
            </div>
            <div className="erp-kpi-card green fin-kpi">
              <span className="kpi-label">CM1 ({cmdData.kpis.cm1_pct}%)</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.cm1)}</span>
              <DeltaBadge pct={cmdData.deltas.cm1_pct} />
            </div>
            <div className="erp-kpi-card blue fin-kpi">
              <span className="kpi-label">CM2 ({cmdData.kpis.cm2_pct}%)</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.cm2)}</span>
              <DeltaBadge pct={cmdData.deltas.cm2_pct} />
            </div>
            <div className="erp-kpi-card clay fin-kpi">
              <span className="kpi-label">CM3 ({cmdData.kpis.cm3_pct}%)</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.cm3)}</span>
              <DeltaBadge pct={cmdData.deltas.cm3_pct} />
            </div>
            <div className="erp-kpi-card fin-kpi">
              <span className="kpi-label">EBITDA / NET PROFIT ({cmdData.kpis.net_profit_pct}%)</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.net_profit)}</span>
              <DeltaBadge pct={cmdData.deltas.net_profit_pct} />
            </div>
            <div className="erp-kpi-card red fin-kpi">
              <span className="kpi-label">TOTAL LOSSES &amp; LEAKAGE</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.total_losses)}</span>
              <span className="kpi-sub">{cmdData.kpis.order_count} orders tracked</span>
            </div>
            <div className="erp-kpi-card green fin-kpi">
              <span className="kpi-label">REALIZED NET CASH FLOW</span>
              <span className="kpi-value">{fmtINR(cmdData.kpis.net_cash_flow)}</span>
              <span className="kpi-sub">EBITDA: {fmtINR(cmdData.kpis.ebitda)}</span>
            </div>
          </div>

          {/* Anomaly Ticker */}
          <div className="erp-panel fin-anomaly-panel">
            <div className="panel-header-row">
              <h3>Real-Time Founder Anomaly Ticker</h3>
              <span className="erp-badge-count">{cmdData.anomalies.length} Active Alerts</span>
            </div>
            {cmdData.anomalies.length === 0 ? (
              <p className="erp-muted">All unit-economics thresholds healthy for selected period.</p>
            ) : (
              <div className="fin-anomaly-list">
                {cmdData.anomalies.map((a, idx) => (
                  <div key={idx} className={`fin-anomaly-item sev-${a.severity.toLowerCase()}`}>
                    <span className="fin-anom-tag">{a.type}</span>
                    <span>{a.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="erp-grid-2">
            <div className="erp-panel">
              <h3>Six-Tier P&amp;L Waterfall Bridge</h3>
              <p className="panel-desc">Decimal-locked cascade from Gross Sales (GMV) to Net Profit (PAT).</p>
              <WaterfallChart bridge={cmdData.waterfall_bridge} />
            </div>

            <div className="erp-panel">
              <h3>Omnichannel Margin Comparison Matrix</h3>
              <p className="panel-desc">B2B Wholesale, Shopify D2C, Amazon, Flipkart &amp; Offline Retail side-by-side.</p>
              <table className="erp-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Orders</th>
                    <th>Net Rev</th>
                    <th>CM1 %</th>
                    <th>CM2 %</th>
                    <th>CM3 (INR)</th>
                    <th>CM3 %</th>
                  </tr>
                </thead>
                <tbody>
                  {cmdData.omnichannel_matrix.map((ch) => (
                    <tr key={ch.channel}>
                      <td><strong>{ch.channel}</strong></td>
                      <td>{ch.orders}</td>
                      <td>{fmtINR(ch.net_revenue)}</td>
                      <td>{ch.cm1_pct}%</td>
                      <td className={ch.cm2_pct < 0 ? 'text-neg' : 'text-pos'}>{ch.cm2_pct}%</td>
                      <td>{fmtINR(ch.cm3)}</td>
                      <td className={ch.cm3_pct < 0 ? 'text-neg' : 'text-pos'}>{ch.cm3_pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* VIEW 1: CM1, CM2 & CM3 UNIT ECONOMICS EXPLORER */}
      {activeTab === 'fin_unit' && unitData && (
        <div className="erp-view-stack">
          <div className="erp-grid-2">
            <div className="erp-panel">
              <h3>Hero SKUs vs. Margin Bleeders (Scatter)</h3>
              <p className="panel-desc">Plotted by Net Revenue vs. CM2 Operational Margin %.</p>
              <ScatterHeroChart skuRankings={unitData.sku_rankings} />
            </div>
            <div className="erp-panel">
              <h3>SKU Profitability Ranking</h3>
              <table className="erp-table">
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>Units</th>
                    <th>Net Rev</th>
                    <th>CM1 %</th>
                    <th>CM2 (INR)</th>
                    <th>CM2 %</th>
                    <th>Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {unitData.sku_rankings.map((s) => (
                    <tr key={s.sku}>
                      <td><strong>{s.sku}</strong></td>
                      <td>{s.units_sold}</td>
                      <td>{fmtINR(s.net_revenue)}</td>
                      <td>{s.cm1_pct}%</td>
                      <td>{fmtINR(s.cm2)}</td>
                      <td>{s.cm2_pct}%</td>
                      <td>
                        <span className={`erp-tag ${s.classification === 'HERO_SKU' ? 'active' : s.classification === 'MARGIN_BLEEDER' ? 'expired' : ''}`}>
                          {s.classification}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="erp-panel">
            <h3>FEFO Formulation Batch COGS &amp; Variance Breakdown</h3>
            <table className="erp-table">
              <thead>
                <tr>
                  <th>Batch ID</th>
                  <th>SKU</th>
                  <th>Channel</th>
                  <th>Order Ref</th>
                  <th>Units</th>
                  <th>Catalog COGS</th>
                  <th>Batch Landed COGS</th>
                  <th>Variance/Unit</th>
                  <th>Line CM2</th>
                </tr>
              </thead>
              <tbody>
                {unitData.batch_variance.map((b, i) => (
                  <tr key={i}>
                    <td><strong>{b.batch_id}</strong></td>
                    <td>{b.sku}</td>
                    <td>{b.channel}</td>
                    <td>{b.order_ref}</td>
                    <td>{b.units}</td>
                    <td>{fmtINR(b.catalog_unit_cost)}</td>
                    <td>{fmtINR(b.actual_batch_unit_cost)}</td>
                    <td className={Number(b.cost_variance_per_unit) > 0 ? 'text-neg' : 'text-pos'}>
                      {fmtINR(b.cost_variance_per_unit)}
                    </td>
                    <td>{fmtINR(b.line_cm2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VIEW 2: OMNICHANNEL & MARKETPLACE SETTLEMENT RECONCILER */}
      {activeTab === 'fin_reconcile' && reconData && (
        <div className="erp-view-stack">
          <div className="erp-kpi-deck">
            <div className="erp-kpi-card">
              <span className="kpi-label">PROVISIONAL HOLDS</span>
              <span className="kpi-value">{reconData.summary.provisional_count} Orders</span>
              <span className="kpi-sub">Expected: {fmtINR(reconData.summary.provisional_hold_amount)}</span>
            </div>
            <div className="erp-kpi-card green">
              <span className="kpi-label">RECONCILED SETTLEMENTS</span>
              <span className="kpi-value">{reconData.summary.reconciled_count} Orders</span>
              <span className="kpi-sub">UTR / POD Verified</span>
            </div>
            <div className="erp-kpi-card red">
              <span className="kpi-label">DISPUTED / OVERCHARGED</span>
              <span className="kpi-value">{reconData.summary.disputed_count} Orders</span>
              <span className="kpi-sub">Discrepancy: {fmtINR(reconData.summary.total_discrepancy)}</span>
            </div>
          </div>

          <div className="erp-panel">
            <div className="panel-header-row">
              <h3>Order-Level Settlement &amp; Fee Variance Ledger</h3>
              <div className="fin-filter-bar">
                <select value={reconChannel} onChange={(e) => setReconChannel(e.target.value)}>
                  <option value="ALL">All Channels</option>
                  <option value="B2B_WHOLESALE">B2B Wholesale</option>
                  <option value="SHOPIFY_D2C">Shopify D2C</option>
                  <option value="AMAZON">Amazon</option>
                  <option value="FLIPKART">Flipkart</option>
                  <option value="MANUAL_OFFLINE">Manual Offline</option>
                </select>
                <select value={reconStatus} onChange={(e) => setReconStatus(e.target.value)}>
                  <option value="ALL">All States</option>
                  <option value="PROVISIONAL">PROVISIONAL</option>
                  <option value="RECONCILED">RECONCILED</option>
                  <option value="DISPUTED">DISPUTED</option>
                </select>
              </div>
            </div>

            <table className="erp-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Channel</th>
                  <th>Order Ref</th>
                  <th>Status</th>
                  <th>Net Rev</th>
                  <th>Fees &amp; Freight</th>
                  <th>Expected Payout</th>
                  <th>Actual Settled</th>
                  <th>UTR / Variance</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {reconData.orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.order_date}</td>
                    <td>{o.channel}</td>
                    <td><strong>{o.external_order_ref}</strong>{o.is_rto ? ' (RTO)' : ''}</td>
                    <td>
                      <span className={`erp-tag ${o.reconciliation_status === 'RECONCILED' ? 'active' : o.reconciliation_status === 'DISPUTED' ? 'expired' : ''}`}>
                        {o.reconciliation_status}
                      </span>
                    </td>
                    <td>{fmtINR(o.net_revenue)}</td>
                    <td>{fmtINR(Number(o.platform_fees) + Number(o.gateway_fees) + Number(o.freight_and_rto))}</td>
                    <td>{fmtINR(o.expected_payout)}</td>
                    <td>{fmtINR(o.actual_payout)}</td>
                    <td>
                      <div>{o.settlement_utr || '—'}</div>
                      {o.discrepancy_reason && <small className="text-neg">{o.discrepancy_reason}</small>}
                    </td>
                    <td>
                      {o.reconciliation_status === 'PROVISIONAL' && (
                        <button
                          className="erp-btn-small"
                          onClick={() => {
                            setReconcileModal(o);
                            setSettleForm({
                              actual_settled_payout: o.expected_payout,
                              settlement_utr: `UTR-${o.external_order_ref}`,
                              platform_commission_fees: o.platform_fees,
                              payment_gateway_fees: o.gateway_fees,
                              outbound_freight_cost: o.freight_and_rto,
                            });
                          }}
                        >
                          Verify UTR
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {reconcileModal && (
            <div className="erp-panel fin-modal-inline">
              <h3>Verify Bank Settlement for {reconcileModal.external_order_ref} ({reconcileModal.channel})</h3>
              <form className="erp-form-grid" onSubmit={handleReconcileSubmit}>
                <label>Actual Bank Payout (INR)
                  <input type="number" step="0.01" required value={settleForm.actual_settled_payout} onChange={(e) => setSettleForm({ ...settleForm, actual_settled_payout: e.target.value })} />
                </label>
                <label>Settlement UTR / Reference
                  <input type="text" required value={settleForm.settlement_utr} onChange={(e) => setSettleForm({ ...settleForm, settlement_utr: e.target.value })} />
                </label>
                <label>Verified Platform Fee
                  <input type="number" step="0.01" value={settleForm.platform_commission_fees} onChange={(e) => setSettleForm({ ...settleForm, platform_commission_fees: e.target.value })} />
                </label>
                <label>Verified Gateway Fee
                  <input type="number" step="0.01" value={settleForm.payment_gateway_fees} onChange={(e) => setSettleForm({ ...settleForm, payment_gateway_fees: e.target.value })} />
                </label>
                <label>Verified Outbound Freight
                  <input type="number" step="0.01" value={settleForm.outbound_freight_cost} onChange={(e) => setSettleForm({ ...settleForm, outbound_freight_cost: e.target.value })} />
                </label>
                <div className="fin-modal-btns">
                  <button type="submit" className="erp-btn-primary">Atomically Reconcile</button>
                  <button type="button" className="erp-btn-secondary" onClick={() => setReconcileModal(null)}>Cancel</button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}

      {/* VIEW 3: TOTAL LOSSES, WASTAGE & LEAKAGE INTELLIGENCE */}
      {activeTab === 'fin_losses' && lossData && (
        <div className="erp-view-stack">
          <div className="erp-kpi-deck">
            <div className="erp-kpi-card red">
              <span className="kpi-label">(A) FEFO EXPIRY &amp; QC WASTAGE</span>
              <span className="kpi-value">{fmtINR(lossData.pillars.fefo_expiry_and_qc)}</span>
            </div>
            <div className="erp-kpi-card clay">
              <span className="kpi-label">(B) LR TRANSIT &amp; RTO BREAKAGE</span>
              <span className="kpi-value">{fmtINR(lossData.pillars.transit_and_rto_breakage)}</span>
            </div>
            <div className="erp-kpi-card">
              <span className="kpi-label">(C) TESTER &amp; PR SEEDING BURN</span>
              <span className="kpi-value">{fmtINR(lossData.pillars.promo_tester_burn)}</span>
            </div>
            <div className="erp-kpi-card red">
              <span className="kpi-label">(D) BAD DEBT, SLA &amp; MANUAL</span>
              <span className="kpi-value">{fmtINR(lossData.pillars.bad_debt_sla_and_manual)}</span>
            </div>
          </div>

          <div className="erp-grid-2">
            <div className="erp-panel">
              <h3>Log Non-System Loss / Write-Off (Maker-Checker)</h3>
              <form className="erp-form-stack" onSubmit={handleCreateLoss}>
                <div className="erp-form-row">
                  <label>Incurred Date
                    <input type="date" required value={lossForm.incurred_date} onChange={(e) => setLossForm({ ...lossForm, incurred_date: e.target.value })} />
                  </label>
                  <label>Category Tag
                    <select value={lossForm.category} onChange={(e) => setLossForm({ ...lossForm, category: e.target.value })}>
                      {LOSS_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </label>
                </div>
                <div className="erp-form-row">
                  <label>Channel
                    <select value={lossForm.channel} onChange={(e) => setLossForm({ ...lossForm, channel: e.target.value })}>
                      {CHANNELS.filter((c) => c.value).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </label>
                  <label>Units Lost
                    <input type="number" min="0" value={lossForm.units_lost} onChange={(e) => setLossForm({ ...lossForm, units_lost: e.target.value })} />
                  </label>
                  <label>Total Loss Value (INR)
                    <input type="number" step="0.01" min="0.01" required value={lossForm.total_loss_amount} onChange={(e) => setLossForm({ ...lossForm, total_loss_amount: e.target.value })} />
                  </label>
                </div>
                <label>Mandatory Reason / Lab Note
                  <textarea rows="2" required value={lossForm.reason_notes} onChange={(e) => setLossForm({ ...lossForm, reason_notes: e.target.value })} />
                </label>
                <button type="submit" className="erp-btn-primary">Submit Loss for Admin Approval</button>
              </form>
            </div>

            <div className="erp-panel">
              <h3>Category Breakdown</h3>
              <table className="erp-table">
                <thead>
                  <tr><th>Category</th><th>Incidents</th><th>Units</th><th>Amount</th></tr>
                </thead>
                <tbody>
                  {lossData.by_category.map((c) => (
                    <tr key={c.category}>
                      <td>{c.label}</td>
                      <td>{c.count}</td>
                      <td>{c.units}</td>
                      <td><strong>{fmtINR(c.amount)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="erp-panel">
            <h3>Approved Losses &amp; Leakage Ledger</h3>
            <table className="erp-table">
              <thead>
                <tr><th>Date</th><th>Category</th><th>Channel</th><th>Batch</th><th>Units</th><th>Loss (INR)</th><th>Source</th><th>Notes</th></tr>
              </thead>
              <tbody>
                {lossData.records.map((r) => (
                  <tr key={r.id}>
                    <td>{r.incurred_date}</td>
                    <td><strong>{r.category_label}</strong></td>
                    <td>{r.channel}</td>
                    <td>{r.batch_id || '—'}</td>
                    <td>{r.units_lost}</td>
                    <td className="text-neg"><strong>{fmtINR(r.total_loss_amount)}</strong></td>
                    <td>{r.is_manual_entry ? 'MANUAL' : 'AUTO HOOK'}</td>
                    <td>{r.reason_notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VIEW 4: MANUAL ENTRY, OFFLINE SALES & OPEX PORTAL */}
      {activeTab === 'fin_manual' && (
        <div className="erp-view-stack">
          <div className="erp-grid-2">
            <div className="erp-panel">
              <h3>Log Offline Store / Exhibition / Gifting Sale</h3>
              <p className="panel-desc">Linking a SKU automatically deducts FEFO batch stock &amp; computes COGS upon Admin approval.</p>
              <form className="erp-form-stack" onSubmit={handleCreateManualSale}>
                <div className="erp-form-row">
                  <label>Sale Date
                    <input type="date" required value={saleForm.sale_date} onChange={(e) => setSaleForm({ ...saleForm, sale_date: e.target.value })} />
                  </label>
                  <label>Reference #
                    <input type="text" required placeholder="EXPO-2026-09" value={saleForm.reference_number} onChange={(e) => setSaleForm({ ...saleForm, reference_number: e.target.value })} />
                  </label>
                </div>
                <label>Customer / Pop-Up / Event Name
                  <input type="text" required placeholder="e.g. Jio World Drive Pop-Up" value={saleForm.customer_or_store_name} onChange={(e) => setSaleForm({ ...saleForm, customer_or_store_name: e.target.value })} />
                </label>
                <div className="erp-form-row">
                  <label>SKU (Auto FEFO Stock)
                    <select value={saleForm.sku} onChange={(e) => setSaleForm({ ...saleForm, sku: e.target.value })}>
                      <option value="">-- Optional Manual COGS Only --</option>
                      {(inventory || []).map((p) => <option key={p.sku} value={p.sku}>{p.sku} ({p.sellable_quantity} avail)</option>)}
                    </select>
                  </label>
                  <label>Qty
                    <input type="number" min="0" value={saleForm.quantity} onChange={(e) => setSaleForm({ ...saleForm, quantity: e.target.value })} />
                  </label>
                </div>
                <div className="erp-form-row">
                  <label>Gross Amount (INR)
                    <input type="number" step="0.01" required value={saleForm.gross_amount} onChange={(e) => setSaleForm({ ...saleForm, gross_amount: e.target.value })} />
                  </label>
                  <label>GST Amount
                    <input type="number" step="0.01" value={saleForm.gst_amount} onChange={(e) => setSaleForm({ ...saleForm, gst_amount: e.target.value })} />
                  </label>
                  <label>Freight &amp; Pack
                    <input type="number" step="0.01" value={saleForm.manual_freight_and_packing} onChange={(e) => setSaleForm({ ...saleForm, manual_freight_and_packing: e.target.value })} />
                  </label>
                </div>
                <button type="submit" className="erp-btn-primary">Submit Sale for Approval</button>
              </form>
            </div>

            <div className="erp-panel">
              <h3>Log Marketing Spend (CM3) &amp; Fixed OPEX (EBITDA)</h3>
              <p className="panel-desc">Multi-day expenses prorate dynamically across the active dashboard date filter.</p>
              <form className="erp-form-stack" onSubmit={handleCreateOpex}>
                <div className="erp-form-row">
                  <label>Period Start
                    <input type="date" required value={opexForm.period_start_date} onChange={(e) => setOpexForm({ ...opexForm, period_start_date: e.target.value })} />
                  </label>
                  <label>Period End
                    <input type="date" required value={opexForm.period_end_date} onChange={(e) => setOpexForm({ ...opexForm, period_end_date: e.target.value })} />
                  </label>
                </div>
                <label>Expense Bucket
                  <select value={opexForm.bucket} onChange={(e) => setOpexForm({ ...opexForm, bucket: e.target.value })}>
                    {EXPENSE_BUCKETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
                  </select>
                </label>
                <div className="erp-form-row">
                  <label>Target Channel
                    <select value={opexForm.target_channel} onChange={(e) => setOpexForm({ ...opexForm, target_channel: e.target.value })}>
                      {CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </label>
                  <label>Amount Excl. GST
                    <input type="number" step="0.01" min="0.01" required value={opexForm.amount_exclusive_gst} onChange={(e) => setOpexForm({ ...opexForm, amount_exclusive_gst: e.target.value })} />
                  </label>
                </div>
                <label>Vendor / Platform Name
                  <input type="text" required placeholder="e.g. Meta Ads Manager / Bhiwandi Landlord" value={opexForm.vendor_or_platform_name} onChange={(e) => setOpexForm({ ...opexForm, vendor_or_platform_name: e.target.value })} />
                </label>
                <button type="submit" className="erp-btn-primary">Submit Spend for Approval</button>
              </form>
            </div>
          </div>

          {/* Maker-Checker Approval Queue */}
          <div className="erp-panel">
            <div className="panel-header-row">
              <h3>Maker-Checker Approval Queue (Active Role: {erpRole})</h3>
              <span className="erp-badge-count">Enforces Admin / Proprietor Sign-Off</span>
            </div>
            <table className="erp-table">
              <thead>
                <tr><th>Type</th><th>Reference / Vendor</th><th>Details</th><th>Amount (INR)</th><th>Status</th><th>Decision</th></tr>
              </thead>
              <tbody>
                {manualSales.map((m) => (
                  <tr key={m.id}>
                    <td><strong>OFFLINE SALE</strong></td>
                    <td>{m.reference_number} — {m.customer_or_store_name}</td>
                    <td>{m.sale_date} {m.sku ? `• SKU ${m.sku} x${m.quantity}` : ''}</td>
                    <td>{fmtINR(m.gross_amount)}</td>
                    <td><span className={`erp-tag ${m.approval_status === 'APPROVED' ? 'active' : m.approval_status === 'REJECTED' ? 'expired' : ''}`}>{m.approval_status}</span></td>
                    <td>
                      {m.approval_status === 'PENDING' && (
                        <div className="fin-action-pair">
                          <button className="erp-btn-small" onClick={() => handleMakerChecker('manual-sale', m.id, 'APPROVE')}>Approve</button>
                          <button className="erp-btn-small danger" onClick={() => handleMakerChecker('manual-sale', m.id, 'REJECT')}>Reject</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {opexEntries.map((o) => (
                  <tr key={o.id}>
                    <td><strong>{o.is_cm3 ? 'CM3 ADS' : 'FIXED OPEX'}</strong></td>
                    <td>{o.vendor_or_platform_name}</td>
                    <td>{o.period_start_date} to {o.period_end_date} ({o.target_channel || 'SHARED'})</td>
                    <td>{fmtINR(o.amount_exclusive_gst)}</td>
                    <td><span className={`erp-tag ${o.approval_status === 'APPROVED' ? 'active' : o.approval_status === 'REJECTED' ? 'expired' : ''}`}>{o.approval_status}</span></td>
                    <td>
                      {o.approval_status === 'PENDING' && (
                        <div className="fin-action-pair">
                          <button className="erp-btn-small" onClick={() => handleMakerChecker('opex', o.id, 'APPROVE')}>Approve</button>
                          <button className="erp-btn-small danger" onClick={() => handleMakerChecker('opex', o.id, 'REJECT')}>Reject</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {(lossData?.pending_approvals || []).map((l) => (
                  <tr key={l.id}>
                    <td><strong>MANUAL LOSS</strong></td>
                    <td>{l.category_label}</td>
                    <td>{l.incurred_date} — {l.reason_notes}</td>
                    <td>{fmtINR(l.total_loss_amount)}</td>
                    <td><span className="erp-tag">{l.approval_status}</span></td>
                    <td>
                      <div className="fin-action-pair">
                        <button className="erp-btn-small" onClick={() => handleMakerChecker('loss', l.id, 'APPROVE')}>Approve</button>
                        <button className="erp-btn-small danger" onClick={() => handleMakerChecker('loss', l.id, 'REJECT')}>Reject</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Bulk CSV Import + Immutable AuditLog */}
          <div className="erp-grid-2">
            <div className="erp-panel">
              <h3>Bulk CSV Importer (Offline Sales / OPEX)</h3>
              <form className="erp-form-stack" onSubmit={handleCsvImport}>
                <select value={csvType} onChange={(e) => setCsvType(e.target.value)}>
                  <option value="opex">Marketing &amp; OPEX CSV (period_start_date,period_end_date,bucket,target_channel,amount_exclusive_gst,vendor_or_platform_name)</option>
                  <option value="sales">Offline Sales CSV (sale_date,reference_number,customer_or_store_name,gross_amount,gst_amount,sku,quantity)</option>
                </select>
                <textarea rows="4" required placeholder="Paste CSV header + rows here..." value={csvContent} onChange={(e) => setCsvContent(e.target.value)} />
                <button type="submit" className="erp-btn-secondary">Import CSV to Pending Queue</button>
              </form>
            </div>
            <div className="erp-panel">
              <h3>Immutable Financial Audit Trail</h3>
              <table className="erp-table">
                <thead><tr><th>Timestamp</th><th>Action</th><th>Entity</th><th>Notes</th></tr></thead>
                <tbody>
                  {auditLogs.slice(0, 10).map((log) => (
                    <tr key={log.id}>
                      <td>{new Date(log.timestamp).toLocaleString()}</td>
                      <td><strong>{log.action}</strong></td>
                      <td>{log.entity_type}</td>
                      <td>{log.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* VIEW 5: CASH FLOW, WORKING CAPITAL & RUNWAY ANALYZER */}
      {activeTab === 'fin_cashflow' && wcData && (
        <div className="erp-view-stack">
          <div className="erp-kpi-deck">
            <div className="erp-kpi-card green">
              <span className="kpi-label">CASH IN BANK BALANCE</span>
              <span className="kpi-value">{fmtINR(wcData.treasury.cash_in_bank_balance)}</span>
              <span className="kpi-sub">Status: {wcData.runway.burn_status}</span>
            </div>
            <div className="erp-kpi-card blue">
              <span className="kpi-label">RUNWAY / OPEX BUFFER</span>
              <span className="kpi-value">{wcData.runway.runway_months} Months</span>
              <span className="kpi-sub">Gross Burn: {fmtINR(wcData.runway.monthly_gross_burn_rate)}/mo</span>
            </div>
            <div className="erp-kpi-card clay">
              <span className="kpi-label">INVENTORY CAPITAL LOCKED</span>
              <span className="kpi-value">{fmtINR(wcData.inventory_capital.total_locked_cogs)}</span>
              <span className="kpi-sub">Sellable: {fmtINR(wcData.inventory_capital.sellable_batch_cogs)}</span>
            </div>
            <div className="erp-kpi-card red">
              <span className="kpi-label">UNCOLLECTED B2B AR / AP PAYABLE</span>
              <span className="kpi-value">{fmtINR(wcData.accrual_vs_cash_bridge.uncollected_b2b_ar)}</span>
              <span className="kpi-sub">AP Payable: {fmtINR(wcData.payables.total_ap)}</span>
            </div>
          </div>

          <div className="erp-grid-2">
            <div className="erp-panel">
              <h3>Accrual P&amp;L vs. Realized Cash Bridge</h3>
              <table className="erp-table">
                <tbody>
                  <tr><td>Accrual Net Profit (PAT)</td><td className="text-pos"><strong>{fmtINR(wcData.accrual_vs_cash_bridge.accrual_net_profit)}</strong></td></tr>
                  <tr><td>Realized Net Cash Flow</td><td><strong>{fmtINR(wcData.accrual_vs_cash_bridge.realized_net_cash_flow)}</strong></td></tr>
                  <tr><td>Uncollected B2B Retailer AR</td><td className="text-neg">{fmtINR(wcData.accrual_vs_cash_bridge.uncollected_b2b_ar)}</td></tr>
                  <tr><td>Pending Marketplace Holds (Provisional)</td><td>{fmtINR(wcData.accrual_vs_cash_bridge.marketplace_pending_payouts)}</td></tr>
                  <tr><td>Unpaid Transporter LR + Vendor OPEX AP</td><td>{fmtINR(wcData.accrual_vs_cash_bridge.unpaid_vendor_transporter_ap)}</td></tr>
                </tbody>
              </table>
              <form className="fin-treasury-form" onSubmit={handleTreasurySave}>
                <label>Update Cash in Bank Balance (INR)</label>
                <div className="fin-action-pair">
                  <input type="number" step="0.01" value={bankInput} onChange={(e) => setBankInput(e.target.value)} />
                  <button type="submit" className="erp-btn-primary">Update Runway</button>
                </div>
              </form>
            </div>

            <div className="erp-panel">
              <h3>B2B Retailer AR Aging (0–90+ Days)</h3>
              <div className="fin-aging-grid">
                <div className="aging-box"><span>0–30 Days</span><strong>{fmtINR(wcData.ar_aging['0_30'])}</strong></div>
                <div className="aging-box warn"><span>31–60 Days</span><strong>{fmtINR(wcData.ar_aging['31_60'])}</strong></div>
                <div className="aging-box danger"><span>61–90 Days</span><strong>{fmtINR(wcData.ar_aging['61_90'])}</strong></div>
                <div className="aging-box danger"><span>90+ Days</span><strong>{fmtINR(wcData.ar_aging['90_plus'])}</strong></div>
              </div>
              <table className="erp-table">
                <thead><tr><th>Order Ref</th><th>Retailer</th><th>Age</th><th>Outstanding</th><th>Action</th></tr></thead>
                <tbody>
                  {wcData.b2b_receivables.map((ar) => (
                    <tr key={ar.order_ref}>
                      <td><strong>{ar.order_ref}</strong></td>
                      <td>{ar.retailer}</td>
                      <td>{ar.age_days}d</td>
                      <td>{fmtINR(ar.outstanding)}</td>
                      <td>
                        <button className="erp-btn-small" onClick={() => handleCollectAR(ar.order_ref, ar.outstanding)}>
                          Mark Collected
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="erp-panel">
            <h3>TMS Transporter LorryReceipts &amp; POD Payables</h3>
            <table className="erp-table">
              <thead><tr><th>LR #</th><th>Order PO</th><th>Transporter</th><th>Mode</th><th>Freight</th><th>POD Status</th><th>AP Status</th><th>Action</th></tr></thead>
              <tbody>
                {lrs.map((lr) => (
                  <tr key={lr.id}>
                    <td><strong>{lr.lr_number}</strong></td>
                    <td>{lr.order_po || '—'}</td>
                    <td>{lr.transporter_name}</td>
                    <td>{lr.freight_mode}</td>
                    <td>{fmtINR(lr.freight_amount)}</td>
                    <td>{lr.pod_status} {lr.pod_damage_cost > 0 ? `(Breakage ${fmtINR(lr.pod_damage_cost)})` : ''}</td>
                    <td><span className={`erp-tag ${lr.transporter_payable_status === 'PAID' ? 'active' : ''}`}>{lr.transporter_payable_status}</span></td>
                    <td>
                      {lr.transporter_payable_status === 'PENDING' && (
                        <button className="erp-btn-small" onClick={() => handleVerifyPod(lr.id)}>
                          Verify POD &amp; Pay
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
