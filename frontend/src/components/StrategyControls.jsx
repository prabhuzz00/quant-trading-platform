import React, { useState, useEffect, useCallback } from 'react';
import { strategiesAPI, riskAPI } from '../api/client';

function pnlClass(val) {
  if (val == null) return 'pnl-neutral';
  return Number(val) >= 0 ? 'pnl-positive' : 'pnl-negative';
}

function pnlSign(val) {
  if (val == null) return '—';
  const n = Number(val);
  return (n >= 0 ? '+₹' : '-₹') + Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const STRATEGY_DESCRIPTIONS = {
  momentum_breakout:   'Trades breakouts above resistance with volume confirmation.',
  mean_reversion:      'Fades extreme moves, betting on reversion to the mean.',
  gap_and_go:          'Capitalises on opening gap continuation patterns.',
  vwap_strategy:       'Enters on VWAP reclaim or rejection setups.',
  orb:                 'Opening Range Breakout — trades the first 15-min range.',
  scalper:             'Ultra-short duration trades targeting 0.2–0.5% moves.',
  swing_trader:        'Holds positions 1–5 days on trend continuation signals.',
  rsi_divergence:      'Detects RSI/price divergence for reversal entries.',
  moving_avg_crossover:'Classic dual-MA crossover with ATR-based stops.',
  options_writer:      'Systematic premium collection via credit spreads.',
};

export default function StrategyControls({ onSelectStrategy }) {
  const [strategies, setStrategies]       = useState([]);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);
  const [toggling, setToggling]           = useState(null);
  const [toast, setToast]                 = useState(null);
  const [tradingActive, setTradingActive] = useState(false);
  const [tradingLoading, setTradingLoading] = useState(false);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchStrategies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await strategiesAPI.getAll();
      setStrategies(Array.isArray(data) ? data : data?.strategies ?? []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTradingState = useCallback(async () => {
    try {
      const data = await riskAPI.getDashboard();
      setTradingActive(data.trading_enabled ?? false);
    } catch (_err) {
      /* non-critical – leave default false */
    }
  }, []);

  useEffect(() => { fetchStrategies(); fetchTradingState(); }, [fetchStrategies, fetchTradingState]);

  const handleToggle = async (name, currentEnabled) => {
    setToggling(name);
    try {
      await strategiesAPI.toggle(name, !currentEnabled);
      setStrategies(prev =>
        prev.map(s => s.name === name ? { ...s, enabled: !currentEnabled } : s)
      );
      showToast(`${name} ${!currentEnabled ? 'enabled' : 'disabled'}.`);
    } catch (e) {
      showToast(e.message, true);
    } finally {
      setToggling(null);
    }
  };

  const handleBulk = async (enable) => {
    const targets = strategies.filter(s => s.enabled !== enable);
    for (const s of targets) {
      try {
        await strategiesAPI.toggle(s.name, enable);
      } catch (_) {
        /* continue */
      }
    }
    fetchStrategies();
    showToast(enable ? 'All strategies enabled.' : 'All strategies disabled.');
  };

  const handleTradingToggle = async () => {
    const nextActive = !tradingActive;
    setTradingLoading(true);
    try {
      await riskAPI.updateConfig({ trading_enabled: nextActive });
      setTradingActive(nextActive);
      showToast(nextActive ? 'Trading started.' : 'Trading stopped.');
    } catch (e) {
      showToast(e.message, true);
    } finally {
      setTradingLoading(false);
    }
  };

  const enabledCount  = strategies.filter(s => s.enabled).length;
  const disabledCount = strategies.length - enabledCount;

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

      <div className="page-header">
        <div>
          <div className="page-title">Strategy Controls</div>
          <div className="page-subtitle">
            {enabledCount} enabled &nbsp;•&nbsp; {disabledCount} disabled
          </div>
        </div>
        <div className="toolbar">
          <button className="btn btn-ghost" onClick={fetchStrategies} disabled={loading}>
            {loading ? '⟳ Loading…' : '⟳ Refresh'}
          </button>
          <button
            className="btn btn-success btn-sm"
            disabled={enabledCount === strategies.length || loading}
            onClick={() => handleBulk(true)}
          >
            Enable All
          </button>
          <button
            className="btn btn-danger btn-sm"
            disabled={disabledCount === strategies.length || loading}
            onClick={() => handleBulk(false)}
          >
            Disable All
          </button>
          <button
            className={`btn${tradingActive ? ' btn-danger' : ' btn-success'}`}
            disabled={tradingLoading}
            onClick={handleTradingToggle}
          >
            {tradingLoading ? '…' : tradingActive ? '⏹ Stop Trading' : '▶ Start Trading'}
          </button>
        </div>
      </div>

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load strategies</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchStrategies}>Retry</button>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading strategies…</div>
        </div>
      )}

      {!error && !loading && strategies.length === 0 && (
        <div className="state-box">
          <div className="state-box-icon">⚙️</div>
          <div className="state-box-text">No strategies found</div>
        </div>
      )}

      {!error && !loading && strategies.length > 0 && (
        <div className="strategy-grid">
          {strategies.map((s) => (
            <div key={s.name} className={`strategy-card${s.enabled ? ' enabled' : ''}`}>
              <div className="strategy-card-header">
                <div>
                  <div className="strategy-name">{s.name}</div>
                  <div className="strategy-desc">
                    {s.description ?? STRATEGY_DESCRIPTIONS[s.name] ?? 'Algorithmic trading strategy.'}
                  </div>
                </div>
                <label className="toggle-wrapper" title={s.enabled ? 'Disable' : 'Enable'}>
                  <div className="toggle">
                    <input
                      type="checkbox"
                      checked={!!s.enabled}
                      disabled={toggling === s.name}
                      onChange={() => handleToggle(s.name, s.enabled)}
                    />
                    <span className="toggle-slider" />
                  </div>
                </label>
              </div>
              <div className="strategy-stats">
                <div className="strategy-stat">
                  <span className="strategy-stat-label">Trades</span>
                  <span className="strategy-stat-value" style={{ color: 'var(--color-blue)' }}>
                    {s.trade_count ?? s.trades ?? 0}
                  </span>
                </div>
                <div className="strategy-stat">
                  <span className="strategy-stat-label">PnL</span>
                  <span className={`strategy-stat-value ${pnlClass(s.pnl ?? s.total_pnl)}`}>
                    {s.pnl != null || s.total_pnl != null ? pnlSign(s.pnl ?? s.total_pnl) : '—'}
                  </span>
                </div>
                {s.win_rate != null && (
                  <div className="strategy-stat">
                    <span className="strategy-stat-label">Win%</span>
                    <span className="strategy-stat-value" style={{ color: 'var(--color-blue)' }}>
                      {Number(s.win_rate).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>
              {onSelectStrategy && (
                <div style={{ marginTop: 12 }}>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ width: '100%' }}
                    onClick={() => onSelectStrategy(s)}
                  >
                    View Details →
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
