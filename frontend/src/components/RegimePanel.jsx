import React, { useState, useEffect, useCallback } from 'react';
import { regimeAPI } from '../api/client';

// ── Helpers ──────────────────────────────────────────────────────────────────

function regimeColor(type) {
  const map = {
    TRENDING_BULLISH:  'var(--color-profit)',
    TRENDING_BEARISH:  'var(--color-loss)',
    SIDEWAYS_LOW_VOL:  'var(--color-blue)',
    SIDEWAYS_HIGH_VOL: '#f59e0b',
    HIGH_VOLATILITY:   '#ef4444',
    UNKNOWN:           'var(--color-muted)',
  };
  return map[type] || 'var(--color-muted)';
}

function regimeIcon(type) {
  const map = {
    TRENDING_BULLISH:  '📈',
    TRENDING_BEARISH:  '📉',
    SIDEWAYS_LOW_VOL:  '➡️',
    SIDEWAYS_HIGH_VOL: '〰️',
    HIGH_VOLATILITY:   '⚡',
    UNKNOWN:           '❓',
  };
  return map[type] || '❓';
}

function regimeLabel(type) {
  return (type || 'UNKNOWN').replace(/_/g, ' ');
}

function scoreColor(score) {
  if (score >= 80) return 'var(--color-profit)';
  if (score >= 50) return '#f59e0b';
  return 'var(--color-loss)';
}

function Badge({ children, color }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 12,
      fontSize: 11,
      fontWeight: 600,
      background: color + '22',
      color: color,
      border: `1px solid ${color}44`,
    }}>
      {children}
    </span>
  );
}

function ScoreBar({ score }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 140 }}>
      <div style={{
        flex: 1, height: 6, background: 'var(--color-border)',
        borderRadius: 3, overflow: 'hidden',
      }}>
        <div style={{
          width: `${score}%`, height: '100%',
          background: scoreColor(score),
          borderRadius: 3,
          transition: 'width 0.4s ease',
        }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color: scoreColor(score), minWidth: 32 }}>
        {score}
      </span>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function RegimePanel() {
  const [status, setStatus]       = useState(null);
  const [config, setConfig]       = useState(null);
  const [loading, setLoading]     = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState(null);
  const [toast, setToast]         = useState(null);

  // Local config edit state
  const [editThreshold, setEditThreshold]   = useState(80);
  const [editInterval, setEditInterval]     = useState(15);
  const [editAutoEnabled, setEditAutoEnabled] = useState(false);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, c] = await Promise.all([regimeAPI.getStatus(), regimeAPI.getConfig()]);
      setStatus(s);
      setConfig(c);
      setEditThreshold(c.score_threshold);
      setEditInterval(c.interval_minutes);
      setEditAutoEnabled(c.enabled);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const s = await regimeAPI.analyze();
      setStatus(s);
      showToast('Regime analysis complete.');
    } catch (e) {
      showToast(e.message, true);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      const updated = await regimeAPI.updateConfig({
        enabled: editAutoEnabled,
        score_threshold: editThreshold,
        interval_minutes: editInterval,
      });
      setConfig(updated);
      showToast('Config saved.');
    } catch (e) {
      showToast(e.message, true);
    } finally {
      setSaving(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Toast */}
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

      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">AI Regime Engine</div>
          <div className="page-subtitle">
            Auto-toggle strategies based on detected market regime
          </div>
        </div>
        <div className="toolbar">
          <button className="btn btn-ghost" onClick={fetchAll} disabled={loading}>
            {loading ? '⟳ Loading…' : '⟳ Refresh'}
          </button>
          <button
            className="btn btn-success"
            onClick={handleAnalyze}
            disabled={analyzing || loading}
          >
            {analyzing ? '⏳ Analyzing…' : '🔍 Run Analysis'}
          </button>
        </div>
      </div>

      {error && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load regime data</div>
          <div className="state-box-sub">{error}</div>
          <button className="btn btn-ghost mt-4" onClick={fetchAll}>Retry</button>
        </div>
      )}

      {loading && !status && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Loading…</div>
        </div>
      )}

      {!loading && !error && status && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* ── Regime Card ── */}
          <div className="card" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
              <div style={{
                fontSize: 48, lineHeight: 1,
              }}>
                {regimeIcon(status.regime_type)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{
                  fontSize: 22, fontWeight: 700,
                  color: regimeColor(status.regime_type),
                  letterSpacing: 1,
                }}>
                  {regimeLabel(status.regime_type)}
                </div>
                <div style={{ color: 'var(--color-muted)', fontSize: 13, marginTop: 4 }}>
                  {status.description}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <Badge color={status.trend === 'bullish' ? 'var(--color-profit)' : status.trend === 'bearish' ? 'var(--color-loss)' : 'var(--color-muted)'}>
                  Trend: {status.trend}
                </Badge>
                <Badge color={status.volatility === 'high' ? '#ef4444' : status.volatility === 'low' ? 'var(--color-blue)' : '#f59e0b'}>
                  Vol: {status.volatility}
                </Badge>
                <Badge color={status.volume === 'high' ? 'var(--color-profit)' : status.volume === 'low' ? 'var(--color-loss)' : 'var(--color-muted)'}>
                  Volume: {status.volume}
                </Badge>
              </div>
            </div>

            {/* Indicator values */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 12, marginTop: 20,
            }}>
              {[
                { label: 'EMA Fast (20)', value: status.ema_fast != null ? status.ema_fast.toFixed(2) : '—' },
                { label: 'EMA Slow (50)', value: status.ema_slow != null ? status.ema_slow.toFixed(2) : '—' },
                { label: 'ATR %',         value: status.atr_pct != null ? status.atr_pct.toFixed(2) + '%' : '—' },
                { label: 'Volume Ratio',  value: status.volume_ratio != null ? status.volume_ratio.toFixed(2) + 'x' : '—' },
                { label: 'Candles Used',  value: status.candle_count },
              ].map(({ label, value }) => (
                <div key={label} style={{
                  background: 'var(--color-surface-alt, #1a1f2e)',
                  borderRadius: 8, padding: '10px 14px',
                }}>
                  <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 4 }}>{label}</div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{value}</div>
                </div>
              ))}
            </div>

            {status.analyzed_at && (
              <div style={{ marginTop: 12, fontSize: 11, color: 'var(--color-muted)' }}>
                Last analyzed: {new Date(status.analyzed_at).toLocaleString()}
              </div>
            )}
            {status.error && (
              <div style={{ marginTop: 10, color: 'var(--color-loss)', fontSize: 12 }}>
                ⚠️ {status.error}
              </div>
            )}
          </div>

          {/* ── Strategy Scores ── */}
          {status.scores && status.scores.length > 0 && (
            <div className="card" style={{ padding: 24 }}>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>
                Strategy Fitness Scores
                <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--color-muted)', fontWeight: 400 }}>
                  (≥ {status.score_threshold} = recommended for this regime)
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[...status.scores]
                  .sort((a, b) => b.score - a.score)
                  .map((s) => (
                    <div key={s.strategy_name} style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 14px',
                      background: 'var(--color-surface-alt, #1a1f2e)',
                      borderRadius: 8,
                      border: s.recommended
                        ? '1px solid var(--color-profit)44'
                        : '1px solid transparent',
                    }}>
                      <div style={{
                        flex: '0 0 180px', fontSize: 13, fontWeight: 600,
                        color: s.recommended ? 'var(--color-profit)' : 'inherit',
                      }}>
                        {s.strategy_name}
                      </div>
                      <div style={{ flex: 1 }}>
                        <ScoreBar score={s.score} />
                      </div>
                      <div style={{ flex: '0 0 90px', textAlign: 'right' }}>
                        {s.recommended
                          ? <Badge color="var(--color-profit)">✓ Enabled</Badge>
                          : <Badge color="var(--color-muted)">Off</Badge>
                        }
                      </div>
                    </div>
                  ))}
              </div>

              {/* Toggle summary */}
              {(status.enabled_by_regime.length > 0 || status.disabled_by_regime.length > 0) && (
                <div style={{ marginTop: 16, fontSize: 12, color: 'var(--color-muted)' }}>
                  {status.enabled_by_regime.length > 0 && (
                    <div>✅ Enabled: {status.enabled_by_regime.join(', ')}</div>
                  )}
                  {status.disabled_by_regime.length > 0 && (
                    <div>🔴 Disabled: {status.disabled_by_regime.join(', ')}</div>
                  )}
                </div>
              )}
              {status.skipped && status.skipped.length > 0 && !status.auto_regime_enabled && (
                <div style={{ marginTop: 8, fontSize: 11, color: 'var(--color-muted)' }}>
                  ℹ️ Auto-regime is off — scores are informational only. Enable below to auto-toggle.
                </div>
              )}
            </div>
          )}

          {/* ── Configuration ── */}
          <div className="card" style={{ padding: 24 }}>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Engine Configuration</div>
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16, alignItems: 'end',
            }}>
              {/* Auto-regime toggle */}
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 6 }}>
                  Auto-Regime (auto-toggle strategies)
                </div>
                <label className="toggle-wrapper" style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                  <div className="toggle">
                    <input
                      type="checkbox"
                      checked={editAutoEnabled}
                      onChange={(e) => setEditAutoEnabled(e.target.checked)}
                    />
                    <span className="toggle-slider" />
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>
                    {editAutoEnabled ? 'Enabled' : 'Disabled'}
                  </span>
                </label>
              </div>

              {/* Score threshold */}
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 6 }}>
                  Score Threshold (0–100)
                </div>
                <input
                  type="number"
                  min={1} max={100}
                  value={editThreshold}
                  onChange={(e) => setEditThreshold(Number(e.target.value))}
                  style={{
                    width: '100%', padding: '8px 12px',
                    background: 'var(--color-surface-alt, #1a1f2e)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 6, color: 'inherit', fontSize: 14,
                  }}
                />
              </div>

              {/* Interval */}
              <div>
                <div style={{ fontSize: 12, color: 'var(--color-muted)', marginBottom: 6 }}>
                  Analysis Interval (minutes)
                </div>
                <input
                  type="number"
                  min={1}
                  value={editInterval}
                  onChange={(e) => setEditInterval(Number(e.target.value))}
                  style={{
                    width: '100%', padding: '8px 12px',
                    background: 'var(--color-surface-alt, #1a1f2e)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 6, color: 'inherit', fontSize: 14,
                  }}
                />
              </div>

              {/* Save button */}
              <div>
                <button
                  className="btn btn-success"
                  style={{ width: '100%' }}
                  onClick={handleSaveConfig}
                  disabled={saving}
                >
                  {saving ? 'Saving…' : '💾 Save Config'}
                </button>
              </div>
            </div>

            {config && (
              <div style={{ marginTop: 14, fontSize: 11, color: 'var(--color-muted)' }}>
                Watching instrument ID <strong>{config.instrument_id}</strong> on{' '}
                <strong>{config.timeframe}-min</strong> candles.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
