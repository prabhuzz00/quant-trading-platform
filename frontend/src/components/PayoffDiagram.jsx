import React, { useState, useEffect, useCallback } from 'react';
import { payoffAPI, catalogAPI } from '../api/client';

export default function PayoffDiagram() {
  const [strategies, setStrategies] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [spot, setSpot] = useState(22000);
  const [iv, setIv] = useState(15);
  const [rangePct, setRangePct] = useState(10);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    catalogAPI.list()
      .then(list => {
        setStrategies(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch(() => {});
  }, []);

  const calculate = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const res = await payoffAPI.calculate({
        strategy_id: selectedId,
        spot: Number(spot),
        iv: Number(iv) / 100,
        spot_range_pct: Number(rangePct),
        dte_values: [0, 3, 7, 14, 30],
        lot_size: 1,
      });
      setResult(res);
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedId, spot, iv, rangePct]);

  const inputStyle = {
    width: '100%', padding: 6, borderRadius: 4,
    border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6', fontSize: 12,
  };

  const CURVE_COLORS = ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#8b5cf6'];

  // Simple SVG chart
  const renderChart = () => {
    if (!result || !result.curves || result.curves.length === 0) return null;

    const W = 700, H = 350, PAD = 50;
    const allPnls = result.curves.flatMap(c => c.points.map(p => p.pnl));
    const allSpots = result.curves[0].points.map(p => p.spot);
    const minPnl = Math.min(...allPnls, 0);
    const maxPnl = Math.max(...allPnls, 0);
    const pnlRange = maxPnl - minPnl || 1;
    const spotMin = allSpots[0];
    const spotMax = allSpots[allSpots.length - 1];
    const spotRange = spotMax - spotMin || 1;

    const sx = (s) => PAD + ((s - spotMin) / spotRange) * (W - 2 * PAD);
    const sy = (p) => H - PAD - ((p - minPnl) / pnlRange) * (H - 2 * PAD);

    const zeroY = sy(0);

    return (
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxHeight: 380, background: '#111827', borderRadius: 8 }}>
        {/* Zero line */}
        <line x1={PAD} y1={zeroY} x2={W - PAD} y2={zeroY} stroke="#4b5563" strokeDasharray="4" />

        {/* Spot marker */}
        <line x1={sx(result.current_spot)} y1={PAD} x2={sx(result.current_spot)} y2={H - PAD}
          stroke="#6b7280" strokeDasharray="4" />
        <text x={sx(result.current_spot)} y={PAD - 6} fill="#9ca3af" fontSize={10} textAnchor="middle">
          Spot: {result.current_spot}
        </text>

        {/* Breakeven markers */}
        {result.breakevens?.map((be, i) => (
          <g key={i}>
            <line x1={sx(be)} y1={PAD} x2={sx(be)} y2={H - PAD} stroke="#f59e0b" strokeDasharray="2" />
            <text x={sx(be)} y={H - PAD + 14} fill="#f59e0b" fontSize={9} textAnchor="middle">BE: {be}</text>
          </g>
        ))}

        {/* Curves */}
        {result.curves.map((curve, ci) => {
          const d = curve.points.map((p, i) =>
            `${i === 0 ? 'M' : 'L'} ${sx(p.spot).toFixed(1)} ${sy(p.pnl).toFixed(1)}`
          ).join(' ');
          return (
            <path key={ci} d={d} fill="none"
              stroke={CURVE_COLORS[ci % CURVE_COLORS.length]}
              strokeWidth={ci === 0 ? 2.5 : 1.5}
              opacity={ci === 0 ? 1 : 0.6} />
          );
        })}

        {/* Axes labels */}
        <text x={W / 2} y={H - 6} fill="#9ca3af" fontSize={10} textAnchor="middle">Spot Price</text>
        <text x={12} y={H / 2} fill="#9ca3af" fontSize={10} textAnchor="middle"
          transform={`rotate(-90, 12, ${H / 2})`}>P&L</text>

        {/* Y axis labels */}
        <text x={PAD - 4} y={sy(maxPnl) + 4} fill="#9ca3af" fontSize={9} textAnchor="end">{maxPnl.toFixed(0)}</text>
        <text x={PAD - 4} y={sy(minPnl) + 4} fill="#9ca3af" fontSize={9} textAnchor="end">{minPnl.toFixed(0)}</text>
        <text x={PAD - 4} y={zeroY + 4} fill="#9ca3af" fontSize={9} textAnchor="end">0</text>

        {/* X axis labels */}
        <text x={sx(spotMin)} y={H - PAD + 14} fill="#9ca3af" fontSize={9} textAnchor="middle">{spotMin.toFixed(0)}</text>
        <text x={sx(spotMax)} y={H - PAD + 14} fill="#9ca3af" fontSize={9} textAnchor="middle">{spotMax.toFixed(0)}</text>
      </svg>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div className="card" style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontWeight: 700, fontSize: 18 }}>📈 Payoff Diagrams</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, alignItems: 'end' }}>
          <div>
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
            <label style={{ fontSize: 11, color: '#9ca3af' }}>Range %</label>
            <input type="number" value={rangePct} onChange={e => setRangePct(e.target.value)} style={inputStyle} />
          </div>
          <button onClick={calculate} disabled={loading}
            style={{
              padding: 8, borderRadius: 6, border: 'none', height: 34,
              background: loading ? '#4b5563' : '#3b82f6', color: '#fff',
              fontWeight: 600, cursor: loading ? 'wait' : 'pointer', fontSize: 13,
            }}>
            {loading ? '⏳' : 'Generate'}
          </button>
        </div>
      </div>

      {result && (
        <>
          {/* Summary */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            <div className="card" style={{ padding: 12, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>Net Premium</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: result.net_premium >= 0 ? '#22c55e' : '#ef4444' }}>
                ₹{result.net_premium?.toFixed(2)}
              </div>
            </div>
            <div className="card" style={{ padding: 12, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>Max Profit</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#22c55e' }}>
                ₹{result.max_profit?.toFixed(2) ?? '∞'}
              </div>
            </div>
            <div className="card" style={{ padding: 12, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>Max Loss</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#ef4444' }}>
                ₹{result.max_loss?.toFixed(2) ?? '∞'}
              </div>
            </div>
            <div className="card" style={{ padding: 12, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>Breakeven(s)</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#f59e0b' }}>
                {result.breakevens?.length > 0 ? result.breakevens.map(b => b.toFixed(0)).join(', ') : '—'}
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="card" style={{ padding: 16, flex: 1 }}>
            {renderChart()}
            {/* Legend */}
            <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 12 }}>
              {result.curves?.map((c, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                  <div style={{ width: 16, height: 3, background: CURVE_COLORS[i % CURVE_COLORS.length], borderRadius: 1 }} />
                  <span style={{ color: '#9ca3af' }}>{c.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Legs detail */}
          <div className="card" style={{ padding: 12 }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>Strategy Legs</h4>
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151' }}>
                  <th style={{ textAlign: 'left', padding: 4 }}>Action</th>
                  <th>Type</th>
                  <th>Strike</th>
                  <th>Qty</th>
                  <th>Entry Premium</th>
                </tr>
              </thead>
              <tbody>
                {result.legs_detail?.map((lg, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #1f2937' }}>
                    <td style={{ padding: 4, color: lg.action === 'BUY' ? '#22c55e' : '#ef4444' }}>{lg.action}</td>
                    <td style={{ textAlign: 'center' }}>{lg.option_type}</td>
                    <td style={{ textAlign: 'center' }}>{lg.strike}</td>
                    <td style={{ textAlign: 'center' }}>{lg.quantity}</td>
                    <td style={{ textAlign: 'center' }}>₹{lg.entry_premium?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="card" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📈</div>
            <div>Select a strategy and click Generate to view the payoff diagram.</div>
          </div>
        </div>
      )}
    </div>
  );
}
