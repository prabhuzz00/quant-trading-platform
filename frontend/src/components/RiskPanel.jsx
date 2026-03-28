import React, { useState, useEffect, useCallback } from 'react';
import { riskAPI } from '../api/client';

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

const RISK_FIELDS = [
  { key: 'max_capital',               label: 'Max Capital (₹)',            type: 'number', hint: 'Total capital allocated' },
  { key: 'max_daily_loss',            label: 'Max Daily Loss (₹)',         type: 'number', hint: 'Stop trading after this loss' },
  { key: 'max_open_trades',           label: 'Max Open Trades',            type: 'number', hint: 'Maximum concurrent open positions' },
  { key: 'max_per_strategy_trades',   label: 'Max Trades / Strategy',      type: 'number', hint: 'Per-strategy concurrent limit' },
  { key: 'max_per_strategy_capital',  label: 'Max Capital / Strategy (₹)', type: 'number', hint: 'Capital limit per strategy' },
  { key: 'max_quantity_per_order',    label: 'Max Qty / Order',            type: 'number', hint: 'Maximum quantity in a single order' },
  { key: 'cooldown_seconds',          label: 'Cooldown (seconds)',          type: 'number', hint: 'Wait time between trades' },
];

export default function RiskPanel() {
  const [config, setConfig]         = useState({});
  const [formValues, setFormValues] = useState({});
  const [dashboard, setDashboard]   = useState(null);
  const [loading, setLoading]       = useState(true);
  const [saving, setSaving]         = useState(false);
  const [ksLoading, setKsLoading]   = useState(false);
  const [error, setError]           = useState(null);
  const [saveMsg, setSaveMsg]       = useState(null);
  const [killSwitchReason, setKillSwitchReason] = useState('');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfg, dash] = await Promise.all([riskAPI.getConfig(), riskAPI.getDashboard()]);
      setConfig(cfg);
      setFormValues({ ...cfg });
      setDashboard(dash);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleChange = (key, value) => {
    setFormValues(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    try {
      const payload = {};
      RISK_FIELDS.forEach(({ key }) => {
        if (formValues[key] !== '' && formValues[key] != null) {
          payload[key] = Number(formValues[key]);
        }
      });
      await riskAPI.updateConfig(payload);
      setSaveMsg({ ok: true, text: 'Risk config saved successfully.' });
      fetchAll();
    } catch (e) {
      setSaveMsg({ ok: false, text: e.message });
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(null), 4000);
    }
  };

  const handleKillSwitch = async () => {
    setKsLoading(true);
    try {
      if (config.kill_switch_active) {
        await riskAPI.deactivateKillSwitch();
      } else {
        await riskAPI.activateKillSwitch(killSwitchReason || 'Manual activation');
        setKillSwitchReason('');
      }
      fetchAll();
    } catch (e) {
      setSaveMsg({ ok: false, text: e.message });
      setTimeout(() => setSaveMsg(null), 4000);
    } finally {
      setKsLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="state-box">
        <div className="spinner" />
        <div className="state-box-text">Loading risk configuration…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="state-box">
        <div className="state-box-icon">⚠️</div>
        <div className="state-box-text">Failed to load risk panel</div>
        <div className="state-box-sub">{error}</div>
        <button className="btn btn-ghost mt-4" onClick={fetchAll}>Retry</button>
      </div>
    );
  }

  const isKsActive = config.kill_switch_active;

  const strategyPnl = dashboard?.strategy_pnl ?? dashboard?.per_strategy_pnl ?? [];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Risk Management</div>
          <div className="page-subtitle">Configure trading limits and kill switch</div>
        </div>
        <button className="btn btn-ghost" onClick={fetchAll}>⟳ Refresh</button>
      </div>

      {/* Metrics */}
      <div className="risk-metrics-grid">
        {[
          { label: 'Daily PnL',     value: pnlSign(dashboard?.daily_pnl),           cls: pnlClass(dashboard?.daily_pnl) },
          { label: 'Open Trades',   value: dashboard?.open_trades_count ?? '—',      cls: 'blue' },
          { label: 'Margin Used',   value: dashboard?.margin_used != null ? `₹${fmt(dashboard.margin_used)}` : '—', cls: '' },
          { label: 'Realized PnL',  value: pnlSign(dashboard?.realized_pnl),         cls: pnlClass(dashboard?.realized_pnl) },
          { label: 'Unrealized PnL',value: pnlSign(dashboard?.unrealized_pnl),       cls: pnlClass(dashboard?.unrealized_pnl) },
          { label: 'Kill Switch',   value: isKsActive ? 'ACTIVE 🔴' : 'Inactive',    cls: isKsActive ? 'loss' : '' },
        ].map(({ label, value, cls }) => (
          <div className="stat-card" key={label}>
            <div className="stat-label">{label}</div>
            <div className={`stat-value ${cls}`} style={{ fontSize: 16 }}>{value}</div>
          </div>
        ))}
      </div>

      <hr className="section-divider" />

      {/* Kill Switch */}
      <div className="card mb-4" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">🔴 Kill Switch</span>
        </div>
        <div className="card-body">
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14 }}>
            Activating the kill switch will halt all new trade entries immediately.
            Existing positions are unaffected until you manually square off.
          </p>
          {!isKsActive && (
            <div style={{ marginBottom: 12 }}>
              <input
                type="text"
                className="form-input"
                style={{ maxWidth: 360 }}
                placeholder="Reason for activation (optional)"
                value={killSwitchReason}
                onChange={e => setKillSwitchReason(e.target.value)}
              />
            </div>
          )}
          <button
            className={`btn btn-lg ${isKsActive ? 'kill-switch-active' : 'kill-switch-inactive'}`}
            onClick={handleKillSwitch}
            disabled={ksLoading}
          >
            {ksLoading ? '…' : isKsActive ? '🔴 Deactivate Kill Switch' : '🟢 Activate Kill Switch'}
          </button>
        </div>
      </div>

      {/* Config Form */}
      <div className="card mb-4" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">Risk Configuration</span>
        </div>
        <div className="card-body">
          {saveMsg && (
            <div style={{
              marginBottom: 14, padding: '8px 14px',
              borderRadius: 'var(--radius-sm)',
              background: saveMsg.ok ? 'var(--color-profit-bg)' : 'var(--color-loss-bg)',
              color: saveMsg.ok ? 'var(--color-profit)' : 'var(--color-loss)',
              fontSize: 13, fontWeight: 500,
            }}>
              {saveMsg.text}
            </div>
          )}
          <form onSubmit={handleSave}>
            <div className="form-grid">
              {RISK_FIELDS.map(({ key, label, type, hint }) => (
                <div className="form-group" key={key}>
                  <label className="form-label">{label}</label>
                  <input
                    type={type}
                    className="form-input"
                    value={formValues[key] ?? ''}
                    min={0}
                    step={key.includes('capital') || key.includes('loss') ? 100 : 1}
                    onChange={e => handleChange(key, e.target.value)}
                  />
                  {hint && <span className="form-hint">{hint}</span>}
                </div>
              ))}
            </div>
            <div style={{ marginTop: 20 }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Saving…' : '💾 Save Configuration'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Per-strategy PnL */}
      {strategyPnl.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Per-Strategy PnL</span>
          </div>
          <div className="table-wrapper" style={{ border: 'none' }}>
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Realized PnL</th>
                  <th>Unrealized PnL</th>
                  <th>Trades</th>
                </tr>
              </thead>
              <tbody>
                {strategyPnl.map((row) => (
                  <tr key={row.strategy_name ?? row.strategy}>
                    <td><span className="badge badge-strategy">{row.strategy_name ?? row.strategy}</span></td>
                    <td className={`td-mono ${pnlClass(row.realized_pnl)}`}>{pnlSign(row.realized_pnl)}</td>
                    <td className={`td-mono ${pnlClass(row.unrealized_pnl)}`}>{pnlSign(row.unrealized_pnl)}</td>
                    <td className="td-mono">{row.trade_count ?? row.trades ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
