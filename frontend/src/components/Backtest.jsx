import React, { useState, useEffect, useCallback } from 'react';
import { backtestAPI, catalogAPI } from '../api/client';

function fmt(v, d = 2) {
  if (v == null) return '—';
  const n = Number(v);
  if (isNaN(n)) return '—';
  return (n >= 0 ? '+' : '') + n.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function pnlColor(v) {
  if (v == null) return '#9ca3af';
  return v >= 0 ? '#22c55e' : '#ef4444';
}

export default function Backtest() {
  const [strategies, setStrategies] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [spot, setSpot] = useState(22000);
  const [iv, setIv] = useState(15);
  const [holdDays, setHoldDays] = useState(7);
  const [slMult, setSlMult] = useState(2.0);
  const [targetPct, setTargetPct] = useState(50);
  const [numTrades, setNumTrades] = useState(52);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('summary');

  useEffect(() => {
    catalogAPI.list()
      .then(list => {
        setStrategies(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch(() => {});
  }, []);

  const runBacktest = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await backtestAPI.run({
        strategy_id: selectedId,
        spot: Number(spot),
        iv: Number(iv) / 100,
        hold_days: Number(holdDays),
        stop_loss_mult: Number(slMult),
        profit_target_pct: Number(targetPct) / 100,
        num_trades: Number(numTrades),
      });
      setResult(res);
      setTab('summary');
    } catch (e) {
      alert('Backtest failed: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedId, spot, iv, holdDays, slMult, targetPct, numTrades]);

  const inputStyle = {
    width: '100%', padding: 6, borderRadius: 4,
    border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6', fontSize: 12,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      {/* Controls */}
      <div className="card" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontWeight: 700, fontSize: 18 }}>🔬 Backtesting Suite</span>
          <span style={{ fontSize: 12, color: '#9ca3af' }}>Black-Scholes Model</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 8, alignItems: 'end' }}>
          <div style={{ gridColumn: 'span 2' }}>
            <label style={{ fontSize: 11, color: '#9ca3af' }}>Strategy</label>
            <select value={selectedId} onChange={e => setSelectedId(e.target.value)}
              style={{ ...inputStyle, padding: 7 }}>
              {strategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#9ca3af' }}>Spot</label>
            <input type="number" value={spot} onChange={e => setSpot(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#9ca3af' }}>IV %</label>
            <input type="number" value={iv} onChange={e => setIv(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#9ca3af' }}>Hold Days</label>
            <input type="number" value={holdDays} onChange={e => setHoldDays(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#9ca3af' }}>Trades</label>
            <input type="number" value={numTrades} onChange={e => setNumTrades(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <button onClick={runBacktest} disabled={loading}
              style={{
                width: '100%', padding: 8, borderRadius: 6, border: 'none',
                background: loading ? '#4b5563' : '#3b82f6', color: '#fff',
                fontWeight: 600, cursor: loading ? 'wait' : 'pointer', fontSize: 13,
              }}>
              {loading ? '⏳ Running…' : '▶ Run'}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {result && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
            {[
              { label: 'Total P&L', value: `₹${fmt(result.total_pnl)}`, color: pnlColor(result.total_pnl) },
              { label: 'Win Rate', value: `${result.win_rate}%`, color: result.win_rate >= 50 ? '#22c55e' : '#ef4444' },
              { label: 'Sharpe', value: result.sharpe_ratio?.toFixed(3), color: result.sharpe_ratio > 0 ? '#22c55e' : '#ef4444' },
              { label: 'Max DD', value: `${result.max_drawdown?.toFixed(1)}%`, color: '#ef4444' },
              { label: 'Profit Factor', value: result.profit_factor?.toFixed(2), color: result.profit_factor > 1 ? '#22c55e' : '#ef4444' },
              { label: 'Trades', value: `${result.winning_trades}W / ${result.losing_trades}L`, color: '#9ca3af' },
            ].map((m, i) => (
              <div key={i} className="card" style={{ padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: m.color }}>{m.value}</div>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="card" style={{ flex: 1, padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', borderBottom: '1px solid #374151' }}>
              {['summary', 'equity', 'monthly', 'trades'].map(t => (
                <button key={t} onClick={() => setTab(t)}
                  style={{
                    padding: '8px 16px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500,
                    background: tab === t ? '#1f2937' : 'transparent',
                    color: tab === t ? '#3b82f6' : '#9ca3af',
                    borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent',
                  }}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
              {tab === 'summary' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 13 }}>
                  <div><strong>Strategy:</strong> {result.strategy_name}</div>
                  <div><strong>Avg P&L:</strong> <span style={{ color: pnlColor(result.avg_pnl) }}>₹{fmt(result.avg_pnl)}</span></div>
                  <div><strong>Best Trade:</strong> <span style={{ color: '#22c55e' }}>₹{fmt(result.max_pnl)}</span></div>
                  <div><strong>Worst Trade:</strong> <span style={{ color: '#ef4444' }}>₹{fmt(result.min_pnl)}</span></div>
                </div>
              )}
              {tab === 'equity' && (
                <div style={{ fontSize: 12 }}>
                  <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 200 }}>
                    {result.equity_curve?.map((p, i) => {
                      const minE = Math.min(...result.equity_curve.map(e => e.equity));
                      const maxE = Math.max(...result.equity_curve.map(e => e.equity));
                      const range = maxE - minE || 1;
                      const h = ((p.equity - minE) / range) * 180 + 20;
                      return (
                        <div key={i} title={`${p.date}: ₹${p.equity.toFixed(0)}`}
                          style={{
                            flex: 1, height: h, minWidth: 2,
                            background: p.equity >= 100000 ? '#22c55e' : '#ef4444',
                            borderRadius: '2px 2px 0 0',
                          }} />
                      );
                    })}
                  </div>
                  <div style={{ textAlign: 'center', color: '#9ca3af', marginTop: 8 }}>Equity Curve</div>
                </div>
              )}
              {tab === 'monthly' && (
                <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #374151' }}>
                      <th style={{ textAlign: 'left', padding: 4 }}>Month</th>
                      <th style={{ textAlign: 'right', padding: 4 }}>P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.monthly_pnl?.map((m, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #1f2937' }}>
                        <td style={{ padding: 4 }}>{m.month}</td>
                        <td style={{ padding: 4, textAlign: 'right', color: pnlColor(m.pnl), fontWeight: 600 }}>₹{fmt(m.pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {tab === 'trades' && (
                <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #374151' }}>
                      <th style={{ textAlign: 'left', padding: 4 }}>#</th>
                      <th style={{ padding: 4 }}>Entry</th>
                      <th style={{ padding: 4 }}>Exit</th>
                      <th style={{ textAlign: 'right', padding: 4 }}>P&L</th>
                      <th style={{ padding: 4 }}>P&L %</th>
                      <th style={{ padding: 4 }}>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades?.map(t => (
                      <tr key={t.trade_id} style={{ borderBottom: '1px solid #1f2937' }}>
                        <td style={{ padding: 4 }}>{t.trade_id}</td>
                        <td style={{ padding: 4 }}>{t.entry_date}</td>
                        <td style={{ padding: 4 }}>{t.exit_date}</td>
                        <td style={{ padding: 4, textAlign: 'right', color: pnlColor(t.pnl), fontWeight: 600 }}>₹{fmt(t.pnl)}</td>
                        <td style={{ padding: 4, textAlign: 'right', color: pnlColor(t.pnl_pct) }}>{fmt(t.pnl_pct, 1)}%</td>
                        <td style={{ padding: 4, fontSize: 10 }}>{t.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="card" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🔬</div>
            <div>Select a strategy and click Run to start backtesting.</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>Uses Black-Scholes model with simulated spot movements.</div>
          </div>
        </div>
      )}
    </div>
  );
}
