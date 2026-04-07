import React, { useState, useEffect, useCallback } from 'react';
import { tradesAPI } from '../api/client';

function fmt(val, decimals = 2) {
  if (val == null || val === '') return '—';
  const n = Number(val);
  if (isNaN(n)) return String(val);
  return n.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function pnlClass(val) {
  if (val == null) return 'pnl-neutral';
  return Number(val) >= 0 ? 'pnl-positive' : 'pnl-negative';
}

function pnlSign(val) {
  if (val == null) return '—';
  const n = Number(val);
  return (n >= 0 ? '+₹' : '-₹') + Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function exitReasonBadge(reason) {
  if (!reason) return <span className="badge badge-closed">—</span>;
  const map = {
    SL_HIT:        'badge-sl',
    TARGET_HIT:    'badge-target',
    MANUAL:        'badge-manual',
    STRATEGY_EXIT: 'badge-strategy',
  };
  return <span className={`badge ${map[reason] || 'badge-closed'}`}>{reason}</span>;
}

function fmtDate(dt) {
  if (!dt) return '—';
  try {
    return new Date(dt).toLocaleString('en-IN', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return dt;
  }
}

export default function ClosedTrades() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateFilter, setDateFilter] = useState('');
  const [strategyFilter, setStrategyFilter] = useState('');

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (dateFilter) params.date = dateFilter;
      if (strategyFilter) params.strategy = strategyFilter;
      const data = await tradesAPI.getClosed(params);
      setTrades(Array.isArray(data) ? data : data?.trades ?? []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [dateFilter, strategyFilter]);

  useEffect(() => { fetchTrades(); }, [fetchTrades]);

  const strategies = [...new Set(trades.map(t => t.strategy_name ?? t.strategy).filter(Boolean))];
  const totalPnl = trades.reduce((acc, t) => acc + (Number(t.realized_pnl ?? t.pnl) || 0), 0);
  const winners = trades.filter(t => Number(t.realized_pnl ?? t.pnl) > 0);
  const losers  = trades.filter(t => Number(t.realized_pnl ?? t.pnl) < 0);
  const winRate = trades.length > 0 ? (winners.length / trades.length * 100).toFixed(1) : null;
  const avgWin  = winners.length > 0 ? winners.reduce((a, t) => a + Number(t.realized_pnl ?? t.pnl), 0) / winners.length : null;
  const avgLoss = losers.length  > 0 ? losers.reduce((a, t)  => a + Number(t.realized_pnl ?? t.pnl), 0) / losers.length  : null;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Closed Trades</div>
          <div className="page-subtitle">{trades.length} trade{trades.length !== 1 ? 's' : ''}</div>
        </div>
        <button className="btn btn-ghost" onClick={fetchTrades} disabled={loading}>
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
      </div>

      {/* Summary */}
      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="stat-card">
          <div className="stat-label">Total Realized PnL</div>
          <div className={`stat-value ${pnlClass(totalPnl)}`} style={{ fontSize: 18 }}>{pnlSign(totalPnl)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value blue">{winRate != null ? `${winRate}%` : '—'}</div>
          <div className="stat-sub">{winners.length}W / {losers.length}L</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg Profit</div>
          <div className={`stat-value ${pnlClass(avgWin)}`}>{avgWin != null ? pnlSign(avgWin) : '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg Loss</div>
          <div className={`stat-value ${pnlClass(avgLoss)}`}>{avgLoss != null ? pnlSign(avgLoss) : '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Trades</div>
          <div className="stat-value">{trades.length}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-row mb-4">
        <input
          type="date"
          className="form-input"
          value={dateFilter}
          onChange={e => setDateFilter(e.target.value)}
          title="Filter by date"
        />
        <select
          className="form-input"
          value={strategyFilter}
          onChange={e => setStrategyFilter(e.target.value)}
        >
          <option value="">All Strategies</option>
          {strategies.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        {(dateFilter || strategyFilter) && (
          <button className="btn btn-ghost btn-sm" onClick={() => { setDateFilter(''); setStrategyFilter(''); }}>
            Clear
          </button>
        )}
      </div>

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load closed trades</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchTrades}>Retry</button>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading closed trades…</div>
        </div>
      )}

      {!error && !loading && trades.length === 0 && (
        <div className="state-box">
          <div className="state-box-icon">📭</div>
          <div className="state-box-text">No closed trades found</div>
          <div className="state-box-sub">Try adjusting the date or strategy filter.</div>
        </div>
      )}

      {!error && !loading && trades.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Avg Entry Price</th>
                <th>Limit Price</th>
                <th>Realized PnL</th>
                <th>Exit Reason</th>
                <th>Strategy</th>
                <th>Closed At</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const pnl = Number(trade.realized_pnl ?? trade.pnl) || 0;
                return (
                  <tr key={trade.order_id ?? trade.id} className={pnl >= 0 ? 'row-profit' : 'row-loss'}>
                    <td><strong>{trade.symbol}</strong></td>
                    <td>
                      <span className={`badge ${trade.action === 'BUY' ? 'badge-profit' : 'badge-loss'}`}>
                        {trade.action}
                      </span>
                    </td>
                    <td className="td-mono">{trade.filled_qty ?? trade.quantity ?? '—'}</td>
                    <td className="td-mono">₹{fmt(trade.avg_price)}</td>
                    <td className="td-mono">₹{fmt(trade.limit_price)}</td>
                    <td className={`td-mono ${pnlClass(pnl)}`} style={{ fontWeight: 600 }}>
                      {pnlSign(pnl)}
                    </td>
                    <td>{exitReasonBadge(trade.reason)}</td>
                    <td>
                      <span className="badge badge-strategy">{trade.strategy_name ?? trade.strategy ?? '—'}</span>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      {fmtDate(trade.updated_at ?? trade.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
