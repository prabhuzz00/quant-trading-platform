import React, { useState, useCallback } from 'react';
import { catalogAPI } from '../api/client';

function fmt(v, d = 4) {
  if (v == null) return '—';
  return Number(v).toFixed(d);
}

export default function GreeksAnalysis() {
  const [mode, setMode] = useState('single'); // 'single' or 'strategy'
  // Single option
  const [spot, setSpot] = useState(22000);
  const [strike, setStrike] = useState(22000);
  const [tte, setTte] = useState(7);
  const [iv, setIv] = useState(15);
  const [isCall, setIsCall] = useState(true);
  const [singleResult, setSingleResult] = useState(null);

  // Strategy
  const [stratSpot, setStratSpot] = useState(22000);
  const [stratIv, setStratIv] = useState(15);
  const [stratTte, setStratTte] = useState(7);
  const [legs, setLegs] = useState([
    { action: 'SELL', option_type: 'CE', strike: 22100, quantity: 1 },
    { action: 'SELL', option_type: 'PE', strike: 21900, quantity: 1 },
  ]);
  const [stratResult, setStratResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const calcSingle = useCallback(async () => {
    setLoading(true);
    try {
      const res = await catalogAPI.optionPrice({
        spot: Number(spot),
        strike: Number(strike),
        tte: Number(tte) / 365,
        iv: Number(iv) / 100,
        is_call: isCall,
      });
      setSingleResult(res);
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [spot, strike, tte, iv, isCall]);

  const calcStrategy = useCallback(async () => {
    setLoading(true);
    try {
      const res = await catalogAPI.greeks({
        spot: Number(stratSpot),
        strikes: legs.map(l => Number(l.strike)),
        option_types: legs.map(l => l.option_type),
        actions: legs.map(l => l.action),
        quantities: legs.map(l => Number(l.quantity)),
        tte: Number(stratTte) / 365,
        iv: Number(stratIv) / 100,
      });
      setStratResult(res);
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [stratSpot, stratIv, stratTte, legs]);

  const updateLeg = (idx, field, value) => {
    const updated = [...legs];
    updated[idx] = { ...updated[idx], [field]: value };
    setLegs(updated);
  };

  const addLeg = () => setLegs([...legs, { action: 'BUY', option_type: 'CE', strike: Number(stratSpot), quantity: 1 }]);
  const removeLeg = (idx) => { if (legs.length > 1) setLegs(legs.filter((_, i) => i !== idx)); };

  const inputStyle = {
    width: '100%', padding: 6, borderRadius: 4,
    border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6', fontSize: 12,
  };

  const greekBox = (label, value, color) => (
    <div className="card" style={{ padding: 12, textAlign: 'center' }}>
      <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: color || '#f3f4f6' }}>{value}</div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div className="card" style={{ padding: '12px 16px' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontWeight: 700, fontSize: 18 }}>⚛️ Greeks Analysis</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
            <button onClick={() => setMode('single')}
              style={{
                padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12,
                background: mode === 'single' ? '#3b82f6' : '#374151',
                color: mode === 'single' ? '#fff' : '#9ca3af',
              }}>Single Option</button>
            <button onClick={() => setMode('strategy')}
              style={{
                padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12,
                background: mode === 'strategy' ? '#3b82f6' : '#374151',
                color: mode === 'strategy' ? '#fff' : '#9ca3af',
              }}>Multi-Leg Strategy</button>
          </div>
        </div>
      </div>

      {mode === 'single' && (
        <>
          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8, alignItems: 'end' }}>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>Spot</label>
                <input type="number" value={spot} onChange={e => setSpot(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>Strike</label>
                <input type="number" value={strike} onChange={e => setStrike(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>DTE</label>
                <input type="number" value={tte} onChange={e => setTte(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>IV %</label>
                <input type="number" value={iv} onChange={e => setIv(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>Type</label>
                <select value={isCall ? 'CE' : 'PE'} onChange={e => setIsCall(e.target.value === 'CE')}
                  style={{ ...inputStyle, padding: 7 }}>
                  <option value="CE">Call (CE)</option>
                  <option value="PE">Put (PE)</option>
                </select>
              </div>
              <button onClick={calcSingle} disabled={loading}
                style={{
                  padding: 8, borderRadius: 6, border: 'none',
                  background: '#3b82f6', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13,
                }}>Calculate</button>
            </div>
          </div>
          {singleResult && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
              {greekBox('Price', `₹${fmt(singleResult.price, 2)}`, '#f3f4f6')}
              {greekBox('Delta (Δ)', fmt(singleResult.delta), '#3b82f6')}
              {greekBox('Gamma (Γ)', fmt(singleResult.gamma, 6), '#8b5cf6')}
              {greekBox('Theta (Θ)', fmt(singleResult.theta), singleResult.theta < 0 ? '#ef4444' : '#22c55e')}
              {greekBox('Vega (ν)', fmt(singleResult.vega), '#f59e0b')}
              {greekBox('Rho (ρ)', fmt(singleResult.rho), '#06b6d4')}
            </div>
          )}
        </>
      )}

      {mode === 'strategy' && (
        <>
          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 8, alignItems: 'end', marginBottom: 12 }}>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>Spot</label>
                <input type="number" value={stratSpot} onChange={e => setStratSpot(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>IV %</label>
                <input type="number" value={stratIv} onChange={e => setStratIv(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#9ca3af' }}>DTE</label>
                <input type="number" value={stratTte} onChange={e => setStratTte(e.target.value)} style={inputStyle} />
              </div>
              <button onClick={calcStrategy} disabled={loading}
                style={{
                  padding: 8, borderRadius: 6, border: 'none', height: 34,
                  background: '#3b82f6', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13,
                }}>Calculate</button>
            </div>

            <div style={{ fontSize: 12, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>Strategy Legs</strong>
              <button onClick={addLeg}
                style={{
                  padding: '4px 12px', borderRadius: 4, border: 'none',
                  background: '#22c55e', color: '#fff', fontSize: 11, cursor: 'pointer',
                }}>+ Add Leg</button>
            </div>

            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #374151' }}>
                  <th style={{ textAlign: 'left', padding: 4 }}>Action</th>
                  <th>Type</th>
                  <th>Strike</th>
                  <th>Qty</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {legs.map((leg, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #1f2937' }}>
                    <td style={{ padding: 4 }}>
                      <select value={leg.action} onChange={e => updateLeg(i, 'action', e.target.value)}
                        style={{ ...inputStyle, width: 80 }}>
                        <option value="BUY">BUY</option>
                        <option value="SELL">SELL</option>
                      </select>
                    </td>
                    <td style={{ padding: 4 }}>
                      <select value={leg.option_type} onChange={e => updateLeg(i, 'option_type', e.target.value)}
                        style={{ ...inputStyle, width: 60 }}>
                        <option value="CE">CE</option>
                        <option value="PE">PE</option>
                      </select>
                    </td>
                    <td style={{ padding: 4 }}>
                      <input type="number" value={leg.strike} onChange={e => updateLeg(i, 'strike', e.target.value)}
                        style={{ ...inputStyle, width: 90 }} />
                    </td>
                    <td style={{ padding: 4 }}>
                      <input type="number" value={leg.quantity} onChange={e => updateLeg(i, 'quantity', e.target.value)}
                        style={{ ...inputStyle, width: 50 }} />
                    </td>
                    <td style={{ padding: 4 }}>
                      <button onClick={() => removeLeg(i)} disabled={legs.length <= 1}
                        style={{
                          padding: '2px 8px', borderRadius: 4, border: 'none',
                          background: '#ef4444', color: '#fff', fontSize: 10, cursor: 'pointer',
                          opacity: legs.length <= 1 ? 0.4 : 1,
                        }}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {stratResult && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
                {greekBox('Net Price', `₹${fmt(stratResult.net_price, 2)}`, '#f3f4f6')}
                {greekBox('Net Delta', fmt(stratResult.net_delta), '#3b82f6')}
                {greekBox('Net Gamma', fmt(stratResult.net_gamma, 6), '#8b5cf6')}
                {greekBox('Net Theta', fmt(stratResult.net_theta), stratResult.net_theta < 0 ? '#ef4444' : '#22c55e')}
                {greekBox('Net Vega', fmt(stratResult.net_vega), '#f59e0b')}
                {greekBox('Net Rho', fmt(stratResult.net_rho), '#06b6d4')}
              </div>
              <div className="card" style={{ padding: 12 }}>
                <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>Per-Leg Greeks</h4>
                <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #374151' }}>
                      <th style={{ textAlign: 'left', padding: 4 }}>Leg</th>
                      <th>Action</th>
                      <th>Type</th>
                      <th>Strike</th>
                      <th>Price</th>
                      <th>Delta</th>
                      <th>Gamma</th>
                      <th>Theta</th>
                      <th>Vega</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stratResult.legs?.map((lg, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #1f2937' }}>
                        <td style={{ padding: 4 }}>{lg.description}</td>
                        <td style={{ textAlign: 'center', color: lg.action === 'BUY' ? '#22c55e' : '#ef4444' }}>{lg.action}</td>
                        <td style={{ textAlign: 'center' }}>{lg.option_type}</td>
                        <td style={{ textAlign: 'center' }}>{lg.strike}</td>
                        <td style={{ textAlign: 'center' }}>₹{fmt(lg.price, 2)}</td>
                        <td style={{ textAlign: 'center' }}>{fmt(lg.delta)}</td>
                        <td style={{ textAlign: 'center' }}>{fmt(lg.gamma, 6)}</td>
                        <td style={{ textAlign: 'center', color: lg.theta < 0 ? '#ef4444' : '#22c55e' }}>{fmt(lg.theta)}</td>
                        <td style={{ textAlign: 'center' }}>{fmt(lg.vega)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
