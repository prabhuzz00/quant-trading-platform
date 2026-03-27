import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { riskAPI } from '../api/client';

function pnlClass(val) {
  if (val == null) return 'pnl-neutral';
  return Number(val) >= 0 ? 'pnl-positive' : 'pnl-negative';
}

function pnlSign(val) {
  if (val == null) return '—';
  const n = Number(val);
  return (n >= 0 ? '+₹' : '-₹') + Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { name, value } = payload[0];
  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-sm)', padding: '8px 12px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 2 }}>{name}</div>
      <div style={{ fontWeight: 600, color: value >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
        {pnlSign(value)}
      </div>
    </div>
  );
}

export default function LivePnL({ dashboardData }) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await riskAPI.getDashboard();
      setDashboard(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  // Prefer live WS data, fall back to polled REST data
  const data = dashboardData ?? dashboard;

  const dailyPnl      = data?.daily_pnl ?? data?.pnl?.daily_realized;
  const realizedPnl   = data?.realized_pnl ?? data?.pnl?.realized;
  const unrealizedPnl = data?.unrealized_pnl ?? data?.pnl?.unrealized;
  const openTrades    = data?.open_trades_count ?? data?.open_trades;
  const closedTrades  = data?.closed_trades_count ?? data?.closed_trades;

  const strategyPnlRaw = data?.strategy_pnl ?? data?.per_strategy_pnl ?? [];
  const chartData = strategyPnlRaw.map(s => ({
    name: s.strategy_name ?? s.strategy ?? 'Unknown',
    value: Number(s.realized_pnl ?? s.pnl ?? 0),
  }));

  if (loading && !data) {
    return (
      <div className="state-box">
        <div className="spinner" />
        <div className="state-box-text">Loading dashboard…</div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="state-box">
        <div className="state-box-icon">⚠️</div>
        <div className="state-box-text">Failed to load dashboard</div>
        <div className="state-box-sub">{error}</div>
        <button className="btn btn-ghost mt-4" onClick={fetchDashboard}>Retry</button>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Live Dashboard</div>
          <div className="page-subtitle">Real-time PnL and trading activity</div>
        </div>
        <button className="btn btn-ghost" onClick={fetchDashboard} disabled={loading}>
          {loading ? '⟳ Updating…' : '⟳ Refresh'}
        </button>
      </div>

      {/* Daily PnL Hero */}
      <div style={{
        background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)', padding: '28px 28px 24px',
        marginBottom: 20, textAlign: 'center',
      }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
          Today's PnL
        </div>
        <div style={{
          fontSize: 48, fontWeight: 800,
          color: dailyPnl != null
            ? (Number(dailyPnl) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)')
            : 'var(--text-secondary)',
          fontVariantNumeric: 'tabular-nums', lineHeight: 1.1,
        }}>
          {dailyPnl != null ? pnlSign(dailyPnl) : '—'}
        </div>
        {dailyPnl != null && (
          <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-muted)' }}>
            Realized: <span className={pnlClass(realizedPnl)}>{pnlSign(realizedPnl)}</span>
            &nbsp;&nbsp;•&nbsp;&nbsp;
            Unrealized: <span className={pnlClass(unrealizedPnl)}>{pnlSign(unrealizedPnl)}</span>
          </div>
        )}
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Realized PnL</div>
          <div className={`stat-value ${pnlClass(realizedPnl)}`} style={{ fontSize: 18 }}>
            {pnlSign(realizedPnl)}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Unrealized PnL</div>
          <div className={`stat-value ${pnlClass(unrealizedPnl)}`} style={{ fontSize: 18 }}>
            {pnlSign(unrealizedPnl)}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open Trades</div>
          <div className="stat-value blue">{openTrades ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Closed Trades</div>
          <div className="stat-value" style={{ color: 'var(--text-primary)' }}>{closedTrades ?? '—'}</div>
        </div>
        {data?.margin_used != null && (
          <div className="stat-card">
            <div className="stat-label">Margin Used</div>
            <div className="stat-value" style={{ fontSize: 18 }}>
              ₹{Number(data.margin_used).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </div>
          </div>
        )}
        {data?.kill_switch_active != null && (
          <div className="stat-card">
            <div className="stat-label">Kill Switch</div>
            <div className={`stat-value ${data.kill_switch_active ? 'loss' : ''}`} style={{ fontSize: 15 }}>
              {data.kill_switch_active ? '🔴 ACTIVE' : '🟢 Inactive'}
            </div>
          </div>
        )}
      </div>

      {/* Strategy PnL Chart */}
      {chartData.length > 0 && (
        <div className="card mt-6">
          <div className="card-header">
            <span className="card-title">PnL by Strategy</span>
          </div>
          <div className="card-body" style={{ paddingTop: 8 }}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                <XAxis
                  dataKey="name"
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={{ stroke: 'var(--border-color)' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.value >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
