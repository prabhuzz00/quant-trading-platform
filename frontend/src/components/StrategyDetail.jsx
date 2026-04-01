import React, { useState, useEffect, useCallback } from 'react';
import { strategiesAPI, tradesAPI } from '../api/client';

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

const STRATEGY_DESCRIPTIONS = {
  momentum_breakout:    'Trades breakouts above resistance with volume confirmation.',
  mean_reversion:       'Fades extreme moves, betting on reversion to the mean.',
  gap_and_go:           'Capitalises on opening gap continuation patterns.',
  vwap_strategy:        'Enters on VWAP reclaim or rejection setups.',
  orb:                  'Opening Range Breakout — trades the first 15-min range.',
  scalper:              'Ultra-short duration trades targeting 0.2–0.5% moves.',
  swing_trader:         'Holds positions 1–5 days on trend continuation signals.',
  rsi_divergence:       'Detects RSI/price divergence for reversal entries.',
  moving_avg_crossover: 'Classic dual-MA crossover with ATR-based stops.',
  options_writer:       'Systematic premium collection via credit spreads.',
};

export default function StrategyDetail({ strategyName, strategyInfo, onBack }) {
  const [performance, setPerformance] = useState(null);
  const [openTrades, setOpenTrades] = useState([]);
  const [closedTrades, setClosedTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [perfData, openData, closedData] = await Promise.all([
        strategiesAPI.getPerformance(strategyName),
        tradesAPI.getOpen(),
        tradesAPI.getClosed({ strategy: strategyName }),
      ]);

      setPerformance(perfData);

      const allOpen = Array.isArray(openData) ? openData : openData?.trades ?? [];
      setOpenTrades(allOpen.filter(t => (t.strategy_name ?? t.strategy) === strategyName));

      setClosedTrades(Array.isArray(closedData) ? closedData : closedData?.trades ?? []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [strategyName]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const allTrades = [
    ...openTrades.map(t => ({ ...t, _status: 'OPEN' })),
    ...closedTrades.map(t => ({ ...t, _status: 'CLOSED' })),
  ];

  const displayedTrades =
    activeTab === 'open'   ? openTrades.map(t => ({ ...t, _status: 'OPEN' })) :
    activeTab === 'closed' ? closedTrades.map(t => ({ ...t, _status: 'CLOSED' })) :
    allTrades;

  const closedPnl  = closedTrades.reduce((acc, t) => acc + (Number(t.realized_pnl) || 0), 0);
  const openPnl    = openTrades.reduce((acc, t)   => acc + (Number(t.unrealized_pnl) || 0), 0);
  const totalPnl   = performance?.total_pnl ?? (closedPnl + openPnl);
  const winners    = closedTrades.filter(t => Number(t.realized_pnl) > 0);
  const losers     = closedTrades.filter(t => Number(t.realized_pnl) < 0);
  const winRate    = closedTrades.length > 0 ? (winners.length / closedTrades.length * 100).toFixed(1) : null;
  const avgWin     = winners.length > 0 ? winners.reduce((a, t) => a + Number(t.realized_pnl), 0) / winners.length : null;
  const avgLoss    = losers.length  > 0 ? losers.reduce((a, t)  => a + Number(t.realized_pnl), 0) / losers.length  : null;

  const description = strategyInfo?.description ?? STRATEGY_DESCRIPTIONS[strategyName] ?? 'Algorithmic trading strategy.';

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-ghost btn-sm" onClick={onBack} title="Back to Strategies">
            ← Back
          </button>
          <div>
            <div className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {strategyName}
              {strategyInfo != null && (
                <span className={`badge ${strategyInfo.enabled ? 'badge-profit' : 'badge-closed'}`}>
                  {strategyInfo.enabled ? 'Enabled' : 'Disabled'}
                </span>
              )}
            </div>
            <div className="page-subtitle">{description}</div>
          </div>
        </div>
        <button className="btn btn-ghost" onClick={fetchData} disabled={loading}>
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
      </div>

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load strategy data</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchData}>Retry</button>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading strategy details…</div>
        </div>
      )}

      {!error && !loading && (
        <>
          {/* Performance Summary */}
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <div className="stat-card">
              <div className="stat-label">Total PnL</div>
              <div className={`stat-value ${pnlClass(totalPnl)}`}>{pnlSign(totalPnl)}</div>
              <div className="stat-sub">Realized + Unrealized</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Open Trades</div>
              <div className="stat-value blue">{performance?.open_trades ?? openTrades.length}</div>
              <div className="stat-sub pnl-neutral">Unrealized: {pnlSign(openPnl)}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Win Rate</div>
              <div className="stat-value blue">{winRate != null ? `${winRate}%` : '—'}</div>
              <div className="stat-sub">{winners.length}W / {losers.length}L of {closedTrades.length} closed</div>
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
              <div className="stat-value blue">{allTrades.length}</div>
              <div className="stat-sub">{openTrades.length} open • {closedTrades.length} closed</div>
            </div>
          </div>

          {/* Trade Tabs */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {[
              { id: 'all',    label: `All (${allTrades.length})` },
              { id: 'open',   label: `Open (${openTrades.length})` },
              { id: 'closed', label: `Closed (${closedTrades.length})` },
            ].map(tab => (
              <button
                key={tab.id}
                className={`btn btn-sm ${activeTab === tab.id ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Trades Table */}
          {displayedTrades.length === 0 ? (
            <div className="state-box">
              <div className="state-box-icon">📭</div>
              <div className="state-box-text">No trades found</div>
              <div className="state-box-sub">No {activeTab !== 'all' ? activeTab + ' ' : ''}trades for this strategy.</div>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th>Qty</th>
                    <th>Avg Price</th>
                    <th>PnL</th>
                    <th>Exit Reason</th>
                    <th>Status</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedTrades.map((trade) => {
                    const isOpen = trade._status === 'OPEN';
                    const pnl = isOpen
                      ? (Number(trade.unrealized_pnl) || 0)
                      : (Number(trade.realized_pnl) || 0);
                    return (
                      <tr key={trade.id ?? trade.order_id} className={pnl >= 0 ? 'row-profit' : 'row-loss'}>
                        <td><strong>{trade.symbol}</strong></td>
                        <td>
                          <span className={`badge ${(trade.action ?? trade.side) === 'BUY' ? 'badge-profit' : 'badge-loss'}`}>
                            {trade.action ?? trade.side}
                          </span>
                        </td>
                        <td className="td-mono">{trade.quantity ?? trade.qty ?? '—'}</td>
                        <td className="td-mono">₹{fmt(trade.avg_price ?? trade.entry_price)}</td>
                        <td className={`td-mono ${pnlClass(pnl)}`} style={{ fontWeight: 600 }}>
                          {pnlSign(pnl)}
                        </td>
                        <td>{isOpen ? <span className="badge badge-open">OPEN</span> : exitReasonBadge(trade.exit_reason ?? trade.reason)}</td>
                        <td>
                          <span className={`badge badge-${(trade._status).toLowerCase()}`}>
                            {trade._status}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          {fmtDate(trade.created_at ?? trade.entry_time)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
