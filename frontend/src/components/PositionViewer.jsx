import React, { useState, useEffect, useCallback, useRef } from 'react';
import { positionsAPI } from '../api/client';

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

const REFRESH_INTERVAL = 30_000;

export default function PositionViewer() {
  const [positions, setPositions] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const timerRef = useRef(null);

  const fetchPositions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await positionsAPI.getAll();
      const list = Array.isArray(data) ? data : data?.positions ?? data?.data ?? [];
      setPositions(Array.isArray(list) ? list : []);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    timerRef.current = setInterval(fetchPositions, REFRESH_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [fetchPositions]);

  const totalMtm = positions.reduce((acc, p) => acc + (Number(p.mtm_pnl ?? p.realized_mtm ?? 0)), 0);
  const netQtyNonZero = positions.filter(p => Number(p.net_qty ?? p.net_quantity ?? 0) !== 0).length;

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Positions</div>
          <div className="page-subtitle">
            {positions.length} position{positions.length !== 1 ? 's' : ''}
            {netQtyNonZero > 0 && ` • ${netQtyNonZero} open`}
            {lastRefresh && (
              <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>
                Last updated {lastRefresh.toLocaleTimeString('en-IN')}
              </span>
            )}
          </div>
        </div>
        <div className="toolbar">
          <button className="btn btn-ghost" onClick={fetchPositions} disabled={loading}>
            {loading ? '⟳ Refreshing…' : '⟳ Refresh'}
          </button>
        </div>
      </div>

      {positions.length > 0 && (
        <div className="stat-grid" style={{ marginBottom: 16 }}>
          <div className="stat-card">
            <div className="stat-label">Total MTM PnL</div>
            <div className={`stat-value ${pnlClass(totalMtm)}`} style={{ fontSize: 18 }}>
              {pnlSign(totalMtm)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Total Positions</div>
            <div className="stat-value blue">{positions.length}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Open Net Positions</div>
            <div className="stat-value">{netQtyNonZero}</div>
          </div>
        </div>
      )}

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load positions</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchPositions}>Retry</button>
        </div>
      )}

      {!error && loading && positions.length === 0 && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading positions…</div>
        </div>
      )}

      {!error && !loading && positions.length === 0 && (
        <div className="state-box">
          <div className="state-box-icon">📋</div>
          <div className="state-box-text">No positions found</div>
          <div className="state-box-sub">No positions are currently available from the broker.</div>
        </div>
      )}

      {positions.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Buy Qty</th>
                <th>Sell Qty</th>
                <th>Net Qty</th>
                <th>Avg Buy Price</th>
                <th>Avg Sell Price</th>
                <th>MTM PnL</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, i) => {
                const netQty  = Number(pos.net_qty ?? pos.net_quantity ?? 0);
                const mtmPnl  = pos.mtm_pnl ?? pos.realized_mtm;
                return (
                  <tr key={pos.symbol ?? i}>
                    <td><strong>{pos.symbol}</strong></td>
                    <td className="td-mono">{pos.buy_qty ?? pos.buy_quantity ?? '—'}</td>
                    <td className="td-mono">{pos.sell_qty ?? pos.sell_quantity ?? '—'}</td>
                    <td className="td-mono" style={{ fontWeight: 600, color: netQty > 0 ? 'var(--color-profit)' : netQty < 0 ? 'var(--color-loss)' : 'var(--text-secondary)' }}>
                      {netQty > 0 ? `+${netQty}` : netQty}
                    </td>
                    <td className="td-mono">₹{fmt(pos.avg_buy_price)}</td>
                    <td className="td-mono">₹{fmt(pos.avg_sell_price)}</td>
                    <td className={`td-mono ${pnlClass(mtmPnl)}`} style={{ fontWeight: 600 }}>
                      {pnlSign(mtmPnl)}
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
