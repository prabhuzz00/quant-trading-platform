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

function ConfirmModal({ message, onConfirm, onCancel }) {
  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-title">Confirm Action</div>
        <div className="modal-body">{message}</div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className="btn btn-danger" onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
}

export default function OpenTrades() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);
  const [confirm, setConfirm] = useState(null); // { type: 'single'|'all', id?: string }
  const [toast, setToast] = useState(null);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await tradesAPI.getOpen();
      setTrades(Array.isArray(data) ? data : data?.trades ?? []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTrades(); }, [fetchTrades]);

  const handleSquareOff = async (id) => {
    setActionLoading(id);
    try {
      await tradesAPI.squareOff(id);
      showToast('Square off order placed.');
      fetchTrades();
    } catch (e) {
      showToast(e.message, true);
    } finally {
      setActionLoading(null);
      setConfirm(null);
    }
  };

  const handleSquareOffAll = async () => {
    setActionLoading('all');
    try {
      await tradesAPI.squareOffAll();
      showToast('All positions squared off.');
      fetchTrades();
    } catch (e) {
      showToast(e.message, true);
    } finally {
      setActionLoading(null);
      setConfirm(null);
    }
  };

  const totalUnrealizedPnl = trades.reduce((acc, t) => acc + (Number(t.unrealized_pnl) || 0), 0);

  return (
    <div>
      {toast && (
        <div style={{
          position: 'fixed', top: 16, right: 20, zIndex: 2000,
          background: toast.isError ? 'var(--color-loss)' : 'var(--color-profit)',
          color: '#fff', padding: '10px 18px', borderRadius: 'var(--radius-md)',
          fontWeight: 500, fontSize: 13, boxShadow: 'var(--shadow-modal)',
        }}>
          {toast.msg}
        </div>
      )}

      {confirm && confirm.type === 'single' && (
        <ConfirmModal
          message={`Square off trade for ${confirm.symbol}? This will place a market order.`}
          onConfirm={() => handleSquareOff(confirm.id)}
          onCancel={() => setConfirm(null)}
        />
      )}
      {confirm && confirm.type === 'all' && (
        <ConfirmModal
          message="Square off ALL open positions? This will place market orders for every open trade."
          onConfirm={handleSquareOffAll}
          onCancel={() => setConfirm(null)}
        />
      )}

      <div className="page-header">
        <div>
          <div className="page-title">Open Trades</div>
          <div className="page-subtitle">
            {trades.length} position{trades.length !== 1 ? 's' : ''} &nbsp;•&nbsp;
            <span className={pnlClass(totalUnrealizedPnl)}>
              Unrealized PnL: {pnlSign(totalUnrealizedPnl)}
            </span>
          </div>
        </div>
        <div className="toolbar">
          <button className="btn btn-ghost" onClick={fetchTrades} disabled={loading}>
            {loading ? '⟳ Loading…' : '⟳ Refresh'}
          </button>
          <button
            className="btn btn-danger"
            disabled={trades.length === 0 || actionLoading === 'all'}
            onClick={() => setConfirm({ type: 'all' })}
          >
            ⚡ Square Off All
          </button>
        </div>
      </div>

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load open trades</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchTrades}>Retry</button>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading open trades…</div>
        </div>
      )}

      {!error && !loading && trades.length === 0 && (
        <div className="state-box">
          <div className="state-box-icon">📭</div>
          <div className="state-box-text">No open trades</div>
          <div className="state-box-sub">There are currently no open positions.</div>
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
                <th>Entry Price</th>
                <th>LTP</th>
                <th>Unrealized PnL</th>
                <th>Stop Loss</th>
                <th>Target</th>
                <th>Strategy</th>
                <th>State</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const pnl = Number(trade.unrealized_pnl) || 0;
                return (
                  <tr key={trade.id} className={pnl >= 0 ? 'row-profit' : 'row-loss'}>
                    <td><strong>{trade.symbol}</strong></td>
                    <td>
                      <span className={`badge ${trade.side === 'BUY' ? 'badge-profit' : 'badge-loss'}`}>
                        {trade.side}
                      </span>
                    </td>
                    <td className="td-mono">{trade.quantity ?? trade.qty ?? '—'}</td>
                    <td className="td-mono">₹{fmt(trade.entry_price)}</td>
                    <td className="td-mono">₹{fmt(trade.ltp ?? trade.last_price)}</td>
                    <td className={`td-mono ${pnlClass(pnl)}`} style={{ fontWeight: 600 }}>
                      {pnlSign(pnl)}
                    </td>
                    <td className="td-mono pnl-negative">₹{fmt(trade.stop_loss ?? trade.sl)}</td>
                    <td className="td-mono pnl-positive">₹{fmt(trade.target)}</td>
                    <td>
                      <span className="badge badge-strategy">{trade.strategy_name ?? trade.strategy ?? '—'}</span>
                    </td>
                    <td>
                      <span className={`badge badge-${(trade.state ?? 'open').toLowerCase()}`}>
                        {trade.state ?? 'OPEN'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-danger btn-sm"
                        disabled={actionLoading === trade.id}
                        onClick={() => setConfirm({ type: 'single', id: trade.id, symbol: trade.symbol })}
                      >
                        {actionLoading === trade.id ? '…' : 'Square Off'}
                      </button>
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
