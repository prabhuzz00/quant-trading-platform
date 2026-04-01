import React, { useState, useEffect, useCallback, useRef } from 'react';
import { positionsAPI } from '../api/client';

function fmtDate(dt) {
  if (!dt) return '—';
  try {
    return new Date(dt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return dt;
  }
}

function fmt(val, decimals = 2) {
  if (val == null || val === '') return '—';
  const n = Number(val);
  if (isNaN(n)) return String(val);
  return n.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function statusBadge(status) {
  if (!status) return <span className="badge badge-closed">—</span>;
  const s = String(status).toUpperCase();
  const map = {
    FILLED:          'badge-completed',
    PARTIALFILL:     'badge-yellow',
    REJECTED:        'badge-rejected',
    CANCELLED:       'badge-rejected',
    PENDING:         'badge-pending',
    PLACED:          'badge-pending',
    TRIGGER_PENDING: 'badge-pending',
    UNKNOWN:         'badge-closed',
  };
  return <span className={`badge ${map[s] || 'badge-closed'}`}>{s}</span>;
}

const TABS = ['ALL', 'FILLED', 'PENDING', 'REJECTED'];

const FILLED_STATUSES  = new Set(['FILLED', 'PARTIALFILL']);
const PENDING_STATUSES = new Set(['PENDING', 'PLACED', 'TRIGGER_PENDING']);
const REJECTED_STATUSES = new Set(['REJECTED', 'CANCELLED']);

function filterOrders(orders, tab) {
  if (tab === 'ALL') return orders;
  if (tab === 'FILLED')   return orders.filter(o => FILLED_STATUSES.has(String(o.status ?? '').toUpperCase()));
  if (tab === 'PENDING')  return orders.filter(o => PENDING_STATUSES.has(String(o.status ?? '').toUpperCase()));
  if (tab === 'REJECTED') return orders.filter(o => REJECTED_STATUSES.has(String(o.status ?? '').toUpperCase()));
  return orders;
}

const REFRESH_INTERVAL = 30_000;

export default function OrderBook() {
  const [orders, setOrders]         = useState([]);
  const [activeTab, setActiveTab]   = useState('ALL');
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const timerRef = useRef(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await positionsAPI.getOrders();
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data?.orders)
          ? data.orders
          : data?.data?.result ?? [];
      setOrders(list);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
    timerRef.current = setInterval(fetchOrders, REFRESH_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [fetchOrders]);

  const filledCount   = orders.filter(o => FILLED_STATUSES.has(String(o.status ?? '').toUpperCase())).length;
  const rejectedCount = orders.filter(o => REJECTED_STATUSES.has(String(o.status ?? '').toUpperCase())).length;
  const pendingCount  = orders.filter(o => PENDING_STATUSES.has(String(o.status ?? '').toUpperCase())).length;

  const displayed = filterOrders(orders, activeTab);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Order Book</div>
          <div className="page-subtitle">
            {orders.length} orders today &nbsp;•&nbsp;
            <span className="pnl-positive">{filledCount} filled</span>
            &nbsp;/&nbsp;
            <span style={{ color: 'var(--color-yellow)' }}>{pendingCount} pending</span>
            &nbsp;/&nbsp;
            <span className="pnl-negative">{rejectedCount} rejected</span>
            {lastRefresh && (
              <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>
                • Updated {lastRefresh.toLocaleTimeString('en-IN')}
              </span>
            )}
          </div>
        </div>
        <button className="btn btn-ghost" onClick={fetchOrders} disabled={loading}>
          {loading ? '⟳ Refreshing…' : '⟳ Refresh'}
        </button>
      </div>

      {/* Status tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {TABS.map(tab => {
          const counts = { ALL: orders.length, FILLED: filledCount, PENDING: pendingCount, REJECTED: rejectedCount };
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`btn ${activeTab === tab ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: 12, padding: '4px 12px' }}
            >
              {tab} <span style={{ opacity: 0.7, marginLeft: 4 }}>({counts[tab]})</span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load orders</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchOrders}>Retry</button>
        </div>
      )}

      {!error && loading && orders.length === 0 && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading orders…</div>
        </div>
      )}

      {!error && !loading && displayed.length === 0 && (
        <div className="state-box">
          <div className="state-box-icon">📒</div>
          <div className="state-box-text">
            {activeTab === 'ALL' ? 'No orders today' : `No ${activeTab.toLowerCase()} orders`}
          </div>
          <div className="state-box-sub">
            {activeTab === 'ALL'
              ? 'No orders have been placed today via the broker.'
              : `No orders with status "${activeTab}" found.`}
          </div>
        </div>
      )}

      {displayed.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty / Filled</th>
                <th>Order Type</th>
                <th>Price</th>
                <th>Avg Price</th>
                <th>Status</th>
                <th>Reject Reason</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((order, i) => (
                <tr key={order.order_id ?? order.exchange_order_id ?? i}>
                  <td className="td-mono" style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                    {order.order_id ?? '—'}
                  </td>
                  <td><strong>{order.symbol ?? '—'}</strong></td>
                  <td>
                    <span className={`badge ${String(order.side ?? '').toUpperCase() === 'BUY' ? 'badge-profit' : 'badge-loss'}`}>
                      {order.side ?? '—'}
                    </span>
                  </td>
                  <td className="td-mono">
                    {order.quantity ?? '—'}
                    {order.filled_qty != null && order.filled_qty > 0 && (
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}> / {order.filled_qty}</span>
                    )}
                  </td>
                  <td>
                    <span className="badge badge-closed" style={{ fontSize: 10 }}>
                      {order.order_type ?? '—'}
                    </span>
                  </td>
                  <td className="td-mono">
                    {order.price != null && Number(order.price) > 0 ? `₹${fmt(order.price)}` : 'MARKET'}
                  </td>
                  <td className="td-mono">
                    {order.avg_price != null && Number(order.avg_price) > 0 ? `₹${fmt(order.avg_price)}` : '—'}
                  </td>
                  <td>{statusBadge(order.status)}</td>
                  <td className="td-wrap" style={{ color: 'var(--color-loss)', fontSize: 11 }}>
                    {order.reject_reason || '—'}
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                    {fmtDate(order.order_time ?? order.last_update_time)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


