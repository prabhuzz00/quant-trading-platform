import React, { useState, useEffect, useCallback } from 'react';
import { catalogAPI } from '../api/client';

const RISK_COLORS = { Low: '#22c55e', Medium: '#f59e0b', High: '#ef4444' };

function Badge({ text, color }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 12,
      fontSize: 11, fontWeight: 600, background: color || '#374151', color: '#fff',
      marginRight: 4, marginBottom: 2,
    }}>{text}</span>
  );
}

export default function StrategyCatalog() {
  const [strategies, setStrategies] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedCat, setSelectedCat] = useState('All');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [buildResult, setBuildResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Build form
  const [spot, setSpot] = useState(22000);
  const [iv, setIv] = useState(15);
  const [dte, setDte] = useState(7);

  useEffect(() => {
    setLoading(true);
    catalogAPI.categories()
      .then(cats => {
        setCategories(cats);
        const all = cats.flatMap(c => c.strategies);
        setStrategies(all);
        setLoading(false);
      })
      .catch(err => { setError(err.message); setLoading(false); });
  }, []);

  const filtered = useCallback(() => {
    let list = strategies;
    if (selectedCat !== 'All') {
      list = list.filter(s => s.category === selectedCat);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.tags.some(t => t.includes(q))
      );
    }
    return list;
  }, [strategies, selectedCat, search]);

  const handleBuild = async () => {
    if (!selected) return;
    try {
      const res = await catalogAPI.build({
        strategy_id: selected.id,
        spot: Number(spot),
        iv: Number(iv) / 100,
        tte: Number(dte) / 365,
        lot_size: 50,
      });
      setBuildResult(res);
    } catch (e) {
      alert('Build failed: ' + e.message);
    }
  };

  if (loading) return <div className="card" style={{ padding: 32, textAlign: 'center' }}>Loading 77 strategies…</div>;
  if (error) return <div className="card" style={{ padding: 32, color: '#ef4444' }}>Error: {error}</div>;

  const catNames = ['All', ...categories.map(c => c.category)];
  const list = filtered();

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%' }}>
      {/* Left panel — catalog */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div className="card" style={{ padding: '12px 16px', marginBottom: 12 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: 18 }}>📚 Strategy Catalog</span>
            <span style={{ fontSize: 12, color: '#9ca3af' }}>({strategies.length} strategies)</span>
            <input
              value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search strategies…"
              style={{
                marginLeft: 'auto', padding: '6px 12px', borderRadius: 6,
                border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6',
                fontSize: 13, width: 220,
              }}
            />
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 8 }}>
            {catNames.map(cat => (
              <button
                key={cat}
                onClick={() => setSelectedCat(cat)}
                style={{
                  padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  fontSize: 11, fontWeight: 500,
                  background: selectedCat === cat ? '#3b82f6' : '#374151',
                  color: selectedCat === cat ? '#fff' : '#9ca3af',
                }}
              >{cat}</button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, overflow: 'auto' }}>
          <table className="data-table" style={{ width: '100%', fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Strategy</th>
                <th>Category</th>
                <th>Legs</th>
                <th>Risk</th>
                <th>Best When</th>
              </tr>
            </thead>
            <tbody>
              {list.map(s => (
                <tr
                  key={s.id}
                  onClick={() => { setSelected(s); setBuildResult(null); }}
                  style={{
                    cursor: 'pointer',
                    background: selected?.id === s.id ? '#1e3a5f' : undefined,
                  }}
                >
                  <td style={{ fontWeight: 600 }}>{s.name}</td>
                  <td><Badge text={s.category} /></td>
                  <td style={{ textAlign: 'center' }}>{s.legs.length}</td>
                  <td><Badge text={s.risk_level} color={RISK_COLORS[s.risk_level]} /></td>
                  <td style={{ fontSize: 11, color: '#9ca3af', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.best_when}</td>
                </tr>
              ))}
              {list.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#6b7280' }}>No strategies match your filter.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right panel — detail + build */}
      <div style={{ width: 380, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {selected ? (
          <>
            <div className="card" style={{ padding: 16 }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>{selected.name}</h3>
              <p style={{ margin: '0 0 8px', fontSize: 12, color: '#9ca3af' }}>{selected.description}</p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                <Badge text={selected.category} />
                <Badge text={selected.risk_level} color={RISK_COLORS[selected.risk_level]} />
                {selected.tags.map(t => <Badge key={t} text={t} color="#1e40af" />)}
              </div>
              <div style={{ fontSize: 12 }}>
                <div><strong>Greeks:</strong> {selected.greeks_profile}</div>
                <div><strong>Max Profit:</strong> {selected.max_profit}</div>
                <div><strong>Max Loss:</strong> {selected.max_loss}</div>
                <div><strong>Best When:</strong> {selected.best_when}</div>
              </div>
              <h4 style={{ margin: '12px 0 6px', fontSize: 13 }}>Legs ({selected.legs.length})</h4>
              <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #374151' }}>
                    <th style={{ textAlign: 'left', padding: 4 }}>Action</th>
                    <th>Type</th>
                    <th>Strike</th>
                    <th>Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.legs.map((leg, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #1f2937' }}>
                      <td style={{ padding: 4, color: leg.action === 'BUY' ? '#22c55e' : '#ef4444' }}>{leg.action}</td>
                      <td style={{ textAlign: 'center' }}>{leg.option_type}</td>
                      <td style={{ textAlign: 'center' }}>{leg.strike_ref} {leg.strike_offset !== 0 ? (leg.strike_offset > 0 ? '+' : '') + leg.strike_offset : ''}</td>
                      <td style={{ textAlign: 'center' }}>{leg.quantity_ratio}×</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Builder */}
            <div className="card" style={{ padding: 16 }}>
              <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>🔧 Build Strategy</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 8 }}>
                <div>
                  <label style={{ fontSize: 11, color: '#9ca3af' }}>Spot</label>
                  <input type="number" value={spot} onChange={e => setSpot(e.target.value)}
                    style={{ width: '100%', padding: 6, borderRadius: 4, border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6', fontSize: 12 }} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: '#9ca3af' }}>IV %</label>
                  <input type="number" value={iv} onChange={e => setIv(e.target.value)}
                    style={{ width: '100%', padding: 6, borderRadius: 4, border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6', fontSize: 12 }} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: '#9ca3af' }}>DTE</label>
                  <input type="number" value={dte} onChange={e => setDte(e.target.value)}
                    style={{ width: '100%', padding: 6, borderRadius: 4, border: '1px solid #374151', background: '#1f2937', color: '#f3f4f6', fontSize: 12 }} />
                </div>
              </div>
              <button onClick={handleBuild}
                style={{ width: '100%', padding: 8, borderRadius: 6, border: 'none', background: '#3b82f6', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
                Build & Calculate Greeks
              </button>
              {buildResult && (
                <div style={{ marginTop: 12, fontSize: 11 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                    <div>Net Premium: <strong>₹{buildResult.net_premium?.toFixed(2)}</strong></div>
                    <div>Net Delta: <strong>{buildResult.net_delta?.toFixed(4)}</strong></div>
                    <div>Net Gamma: <strong>{buildResult.net_gamma?.toFixed(6)}</strong></div>
                    <div>Net Theta: <strong>{buildResult.net_theta?.toFixed(4)}</strong></div>
                    <div>Net Vega: <strong>{buildResult.net_vega?.toFixed(4)}</strong></div>
                  </div>
                  <h5 style={{ margin: '8px 0 4px' }}>Built Legs</h5>
                  <table style={{ width: '100%', fontSize: 10, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #374151' }}>
                        <th style={{ textAlign: 'left', padding: 2 }}>Action</th>
                        <th>Type</th>
                        <th>Strike</th>
                        <th>Qty</th>
                        <th>Premium</th>
                        <th>Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      {buildResult.legs?.map((leg, i) => (
                        <tr key={i}>
                          <td style={{ padding: 2, color: leg.action === 'BUY' ? '#22c55e' : '#ef4444' }}>{leg.action}</td>
                          <td style={{ textAlign: 'center' }}>{leg.option_type}</td>
                          <td style={{ textAlign: 'center' }}>{leg.strike}</td>
                          <td style={{ textAlign: 'center' }}>{leg.quantity}</td>
                          <td style={{ textAlign: 'center' }}>₹{leg.premium?.toFixed(2)}</td>
                          <td style={{ textAlign: 'center' }}>{leg.delta?.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="card" style={{ padding: 32, textAlign: 'center', color: '#6b7280' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📊</div>
            <div>Select a strategy from the catalog to view details and build it.</div>
          </div>
        )}
      </div>
    </div>
  );
}
