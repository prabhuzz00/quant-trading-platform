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
    COMPLETED:    'badge-completed',
    FILLED:       'badge-completed',
    REJECTED:     'badge-rejected',
    CANCELLED:    'badge-rejected',
    PENDING:      'badge-pending',
    OPEN:         'badge-open',
    PLACED:       'badge-pending',
    PARTIALFILL:  'badge-yellow',
    TRIGGER_PENDING: 'badge-pending',
  };
  return <span className={`badge ${map[s] || 'badge-closed'}`}>{s}</span>;
}

const REFRESH_INTERVAL = 30_000;

export default function OrderBook() {
  const [orders, setOrders]         = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const timerRef = useRef(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await positionsAPI.getOrders();
      setOrders(Array.isArray(data) ? data : data?.orders ?? []);
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

  const completedCount = orders.filter(o => ['COMPLETED', 'FILLED'].includes(String(o.status ?? '').toUpperCase())).length;
  const rejectedCount  = orders.filter(o => ['REJECTED', 'CANCELLED'].includes(String(o.status ?? '').toUpperCase())).length;
  const pendingCount   = orders.length - completedCount - rejectedCount;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Order Book</div>
          <div className="page-subtitle">
            {orders.length} orders today &nbsp;•&nbsp;
            <span className="pnl-positive">{completedCount} filled</span>
            &nbsp;/&nbsp;
            <span className="pnl-negative">{rejectedCount} rejected</span>
            &nbsp;/&nbsp;
            <span style={{ color: 'var(--color-yellow)' }}>{pendingCount} pending</span>
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

      {!error && !loading && orders.length === 0 && (
        <div className="state-box">
          <div className="state-box-icon">📒</div>
          <div className="state-box-text">No orders today</div>
          <div className="state-box-sub">No orders have been placed today via the broker.</div>
        </div>
      )}

      {orders.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Order Type</th>
                <th>Price</th>
                <th>Status</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order, i) => (
                <tr key={order.order_id ?? order.id ?? i}>
                  <td className="td-mono" style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                    {order.order_id ?? order.id ?? '—'}
                  </td>
                  <td><strong>{order.symbol}</strong></td>
                  <td>
                    <span className={`badge ${(order.side ?? order.transaction_type ?? '') === 'BUY' ? 'badge-profit' : 'badge-loss'}`}>
                      {order.side ?? order.transaction_type ?? '—'}
                    </span>
                  </td>
                  <td className="td-mono">{order.quantity ?? order.qty ?? '—'}</td>
                  <td>
                    <span className="badge badge-closed" style={{ fontSize: 10 }}>
                      {order.order_type ?? order.type ?? '—'}
                    </span>
                  </td>
                  <td className="td-mono">
                    {order.price != null && Number(order.price) > 0 ? `₹${fmt(order.price)}` : 'MARKET'}
                  </td>
                  <td>{statusBadge(order.status ?? order.order_status)}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                    {fmtDate(order.order_time ?? order.time ?? order.created_at)}
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
