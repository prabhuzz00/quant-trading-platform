import React, { useState, useEffect, useCallback, useRef } from 'react';
import { manualAPI } from '../api/client';

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtPrice(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (isNaN(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtOi(v) {
  if (v == null) return '—';
  const n = Number(v);
  if (isNaN(n)) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function fmtChange(v) {
  if (v == null) return null;
  const n = Number(v);
  if (isNaN(n)) return null;
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

// ---------------------------------------------------------------------------
// Order Modal
// ---------------------------------------------------------------------------

function OrderModal({ side, row, optType, onClose, onSuccess }) {
  const inst_id    = optType === 'CE' ? row.ce_instrument_id : row.pe_instrument_id;
  const lot_size   = optType === 'CE' ? (row.ce_lot_size ?? 25) : (row.pe_lot_size ?? 25);
  const defaultLtp = optType === 'CE' ? row.ce_ltp : row.pe_ltp;

  const [lots, setLots]             = useState(1);
  const [orderType, setOrderType]   = useState('LIMIT');
  const [limitPrice, setLimitPrice] = useState(defaultLtp != null ? String(defaultLtp) : '');
  const [stopPrice, setStopPrice]   = useState('');
  const [productType, setProductType] = useState('MIS');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState(null);

  const qty = lots * lot_size;

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        exchange_segment:       'NSEFO',
        exchange_instrument_id: inst_id,
        order_side:             side,
        quantity:               qty,
        product_type:           productType,
        order_type:             orderType,
        time_in_force:          'DAY',
        ...(orderType !== 'MARKET' && limitPrice ? { limit_price: parseFloat(limitPrice) } : {}),
        ...((orderType === 'SL' || orderType === 'SL-M') && stopPrice
          ? { stop_price: parseFloat(stopPrice) }
          : {}),
      };
      const result = await manualAPI.placeOrder(payload);
      onSuccess(result?.order_id ?? '');
    } catch (err) {
      setError(err.message || 'Order placement failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span>
            <span className={`badge ${side === 'BUY' ? 'badge-profit' : 'badge-loss'}`}>{side}</span>
            &nbsp; NIFTY {row.strike} {optType}
          </span>
          <button className="btn btn-ghost" style={{ padding: '2px 8px' }} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={submit}>
          <div className="form-grid">
            <label className="form-label">
              Lots
              <input
                className="form-input"
                type="number"
                min={1}
                value={lots}
                onChange={(e) => setLots(Math.max(1, parseInt(e.target.value) || 1))}
              />
              <span className="form-hint">{qty} qty (lot size {lot_size})</span>
            </label>

            <label className="form-label">
              Order Type
              <select
                className="form-input"
                value={orderType}
                onChange={(e) => setOrderType(e.target.value)}
              >
                <option value="LIMIT">LIMIT</option>
                <option value="MARKET">MARKET</option>
                <option value="SL">SL</option>
                <option value="SL-M">SL-M</option>
              </select>
            </label>

            {orderType !== 'MARKET' && (
              <label className="form-label">
                Limit Price (₹)
                <input
                  className="form-input"
                  type="number"
                  step="0.05"
                  min={0}
                  value={limitPrice}
                  onChange={(e) => setLimitPrice(e.target.value)}
                  required={orderType !== 'MARKET'}
                />
              </label>
            )}

            {(orderType === 'SL' || orderType === 'SL-M') && (
              <label className="form-label">
                Stop Price (₹)
                <input
                  className="form-input"
                  type="number"
                  step="0.05"
                  min={0}
                  value={stopPrice}
                  onChange={(e) => setStopPrice(e.target.value)}
                />
              </label>
            )}

            <label className="form-label">
              Product
              <select
                className="form-input"
                value={productType}
                onChange={(e) => setProductType(e.target.value)}
              >
                <option value="MIS">MIS (Intraday)</option>
                <option value="NRML">NRML (Carryforward)</option>
              </select>
            </label>
          </div>

          {error && (
            <div className="alert-error">{error}</div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button
              type="submit"
              className={`btn ${side === 'BUY' ? 'btn-buy' : 'btn-sell'}`}
              disabled={submitting}
              style={{ flex: 1 }}
            >
              {submitting ? 'Placing…' : `Place ${side} Order`}
            </button>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ManualTrading() {
  const [symbol, setSymbol]           = useState('NIFTY');
  const [expiries, setExpiries]       = useState([]);
  const [selectedExpiry, setSelectedExpiry] = useState('');
  const [spotPrice, setSpotPrice]     = useState('');
  const [numStrikes, setNumStrikes]   = useState(10);
  const [chain, setChain]             = useState(null);
  const [loadingExpiries, setLoadingExpiries] = useState(false);
  const [loadingChain, setLoadingChain]       = useState(false);
  const [expiriesError, setExpiriesError]     = useState(null);
  const [chainError, setChainError]           = useState(null);
  const [modal, setModal]             = useState(null); // {side, row, optType}
  const [orderSuccess, setOrderSuccess] = useState(null);

  // Fetch expiries whenever symbol changes
  const fetchExpiries = useCallback(async (sym) => {
    setLoadingExpiries(true);
    setExpiriesError(null);
    setExpiries([]);
    setSelectedExpiry('');
    setChain(null);
    try {
      const data = await manualAPI.getExpiries(sym);
      const list = data?.expiries ?? [];
      setExpiries(list);
      if (list.length > 0) setSelectedExpiry(list[0]);
    } catch (err) {
      setExpiriesError(err.message);
    } finally {
      setLoadingExpiries(false);
    }
  }, []);

  useEffect(() => {
    fetchExpiries(symbol);
  }, [symbol, fetchExpiries]);

  const loadChain = useCallback(async () => {
    if (!selectedExpiry) return;
    setLoadingChain(true);
    setChainError(null);
    setChain(null);
    try {
      const data = await manualAPI.getOptionChain(symbol, selectedExpiry, {
        spotPrice: spotPrice ? parseFloat(spotPrice) : undefined,
        numStrikes,
      });
      setChain(data);
    } catch (err) {
      setChainError(err.message);
    } finally {
      setLoadingChain(false);
    }
  }, [symbol, selectedExpiry, spotPrice, numStrikes]);

  function openModal(side, row, optType) {
    const instId = optType === 'CE' ? row.ce_instrument_id : row.pe_instrument_id;
    if (!instId) return;
    setOrderSuccess(null);
    setModal({ side, row, optType });
  }

  function handleOrderSuccess(orderId) {
    setModal(null);
    setOrderSuccess(`Order placed! ID: ${orderId || 'N/A'}`);
    setTimeout(() => setOrderSuccess(null), 6000);
  }

  const atm = chain?.atm_strike;

  return (
    <div>
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">Manual Trading</div>
          <div className="page-subtitle">View NIFTY option chain and place orders manually</div>
        </div>
      </div>

      {/* Controls */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          {/* Symbol */}
          <label className="form-label" style={{ minWidth: 110 }}>
            Symbol
            <select
              className="form-input"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            >
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
              <option value="FINNIFTY">FINNIFTY</option>
              <option value="MIDCPNIFTY">MIDCPNIFTY</option>
            </select>
          </label>

          {/* Expiry */}
          <label className="form-label" style={{ minWidth: 160 }}>
            Expiry
            <select
              className="form-input"
              value={selectedExpiry}
              onChange={(e) => setSelectedExpiry(e.target.value)}
              disabled={loadingExpiries || expiries.length === 0}
            >
              {loadingExpiries && <option>Loading…</option>}
              {expiriesError && <option>Error loading</option>}
              {expiries.map((exp) => (
                <option key={exp} value={exp}>{exp}</option>
              ))}
            </select>
          </label>

          {/* Spot price */}
          <label className="form-label" style={{ minWidth: 130 }}>
            Spot Price (₹)
            <input
              className="form-input"
              type="number"
              step="0.5"
              min={0}
              placeholder="e.g. 22150"
              value={spotPrice}
              onChange={(e) => setSpotPrice(e.target.value)}
            />
          </label>

          {/* Strikes */}
          <label className="form-label" style={{ minWidth: 110 }}>
            Strikes ±
            <input
              className="form-input"
              type="number"
              min={1}
              max={30}
              value={numStrikes}
              onChange={(e) => setNumStrikes(Math.min(30, Math.max(1, parseInt(e.target.value) || 10)))}
            />
          </label>

          <button
            className="btn btn-primary"
            onClick={loadChain}
            disabled={loadingChain || !selectedExpiry}
            style={{ alignSelf: 'flex-end', marginBottom: 0 }}
          >
            {loadingChain ? '⟳ Loading…' : '⟳ Load Chain'}
          </button>
        </div>

        {expiriesError && (
          <div className="alert-error" style={{ marginTop: 8 }}>
            Failed to load expiries: {expiriesError}
          </div>
        )}
      </div>

      {/* Order success toast */}
      {orderSuccess && (
        <div className="alert-success" style={{ marginBottom: 12 }}>
          ✅ {orderSuccess}
        </div>
      )}

      {/* Chain error */}
      {chainError && (
        <div className="state-box">
          <div className="state-box-icon">⚠️</div>
          <div className="state-box-text">Failed to load option chain</div>
          <div className="state-box-sub">{chainError}</div>
          <button className="btn btn-ghost" style={{ marginTop: 12 }} onClick={loadChain}>Retry</button>
        </div>
      )}

      {/* Loading spinner */}
      {loadingChain && (
        <div className="state-box">
          <div className="spinner" />
          <div className="state-box-text">Fetching option chain…</div>
          <div className="state-box-sub">Downloading master data and live quotes</div>
        </div>
      )}

      {/* Option Chain Table */}
      {!loadingChain && !chainError && chain && (
        <>
          <div style={{ marginBottom: 8, color: 'var(--text-secondary)', fontSize: 12 }}>
            <strong>{chain.symbol}</strong> · {chain.expiry}
            {chain.atm_strike != null && (
              <> · ATM <strong style={{ color: 'var(--color-yellow)' }}>₹{chain.atm_strike.toLocaleString('en-IN')}</strong></>
            )}
            {chain.spot_price != null && (
              <> · Spot <strong>₹{fmtPrice(chain.spot_price)}</strong></>
            )}
            <> · <span style={{ color: 'var(--text-muted)' }}>{chain.rows.length} strikes</span></>
          </div>

          <div className="table-wrapper" style={{ overflowX: 'auto' }}>
            <table style={{ minWidth: 860 }}>
              <thead>
                <tr>
                  {/* CALL side headers */}
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)' }}>OI</th>
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)' }}>Volume</th>
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)' }}>Bid</th>
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)' }}>LTP (CE)</th>
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)' }}>Ask</th>
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)', width: 70 }}>Buy</th>
                  <th style={{ textAlign: 'right', color: 'var(--color-profit)', width: 70 }}>Sell</th>
                  {/* Strike */}
                  <th style={{ textAlign: 'center', color: 'var(--color-yellow)', background: 'var(--bg-tertiary)' }}>Strike</th>
                  {/* PUT side headers */}
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)', width: 70 }}>Buy</th>
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)', width: 70 }}>Sell</th>
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)' }}>Bid</th>
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)' }}>LTP (PE)</th>
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)' }}>Ask</th>
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)' }}>Volume</th>
                  <th style={{ textAlign: 'left', color: 'var(--color-loss)' }}>OI</th>
                </tr>
              </thead>
              <tbody>
                {chain.rows.map((row) => {
                  const isAtm = row.is_atm;
                  const ceChg = fmtChange(row.ce_change_pct);
                  const peChg = fmtChange(row.pe_change_pct);
                  return (
                    <tr
                      key={row.strike}
                      style={
                        isAtm
                          ? { background: 'var(--color-yellow-bg)', fontWeight: 600 }
                          : undefined
                      }
                    >
                      {/* CE OI */}
                      <td className="td-mono" style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {fmtOi(row.ce_oi)}
                      </td>
                      {/* CE Volume */}
                      <td className="td-mono" style={{ textAlign: 'right', color: 'var(--text-muted)' }}>
                        {fmtOi(row.ce_volume)}
                      </td>
                      {/* CE Bid */}
                      <td className="td-mono" style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {fmtPrice(row.ce_bid)}
                      </td>
                      {/* CE LTP */}
                      <td className="td-mono" style={{ textAlign: 'right' }}>
                        {fmtPrice(row.ce_ltp)}
                        {ceChg && (
                          <span style={{ marginLeft: 4, fontSize: 10, color: row.ce_change_pct >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                            {ceChg}
                          </span>
                        )}
                      </td>
                      {/* CE Ask */}
                      <td className="td-mono" style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {fmtPrice(row.ce_ask)}
                      </td>
                      {/* CE Buy */}
                      <td style={{ textAlign: 'right' }}>
                        {row.ce_instrument_id ? (
                          <button className="btn-action btn-buy-sm" onClick={() => openModal('BUY', row, 'CE')}>B</button>
                        ) : '—'}
                      </td>
                      {/* CE Sell */}
                      <td style={{ textAlign: 'right' }}>
                        {row.ce_instrument_id ? (
                          <button className="btn-action btn-sell-sm" onClick={() => openModal('SELL', row, 'CE')}>S</button>
                        ) : '—'}
                      </td>

                      {/* Strike */}
                      <td
                        className="td-mono"
                        style={{
                          textAlign: 'center',
                          fontWeight: 700,
                          background: 'var(--bg-tertiary)',
                          color: isAtm ? 'var(--color-yellow)' : 'var(--text-primary)',
                        }}
                      >
                        {row.strike.toLocaleString('en-IN')}
                        {isAtm && <span style={{ marginLeft: 4, fontSize: 9, color: 'var(--color-yellow)' }}>ATM</span>}
                      </td>

                      {/* PE Buy */}
                      <td style={{ textAlign: 'left' }}>
                        {row.pe_instrument_id ? (
                          <button className="btn-action btn-buy-sm" onClick={() => openModal('BUY', row, 'PE')}>B</button>
                        ) : '—'}
                      </td>
                      {/* PE Sell */}
                      <td style={{ textAlign: 'left' }}>
                        {row.pe_instrument_id ? (
                          <button className="btn-action btn-sell-sm" onClick={() => openModal('SELL', row, 'PE')}>S</button>
                        ) : '—'}
                      </td>
                      {/* PE Bid */}
                      <td className="td-mono" style={{ color: 'var(--text-secondary)' }}>
                        {fmtPrice(row.pe_bid)}
                      </td>
                      {/* PE LTP */}
                      <td className="td-mono">
                        {fmtPrice(row.pe_ltp)}
                        {peChg && (
                          <span style={{ marginLeft: 4, fontSize: 10, color: row.pe_change_pct >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                            {peChg}
                          </span>
                        )}
                      </td>
                      {/* PE Ask */}
                      <td className="td-mono" style={{ color: 'var(--text-secondary)' }}>
                        {fmtPrice(row.pe_ask)}
                      </td>
                      {/* PE Volume */}
                      <td className="td-mono" style={{ color: 'var(--text-muted)' }}>
                        {fmtOi(row.pe_volume)}
                      </td>
                      {/* PE OI */}
                      <td className="td-mono" style={{ color: 'var(--text-secondary)' }}>
                        {fmtOi(row.pe_oi)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Empty state before first load */}
      {!loadingChain && !chainError && !chain && selectedExpiry && (
        <div className="state-box">
          <div className="state-box-icon">📊</div>
          <div className="state-box-text">Select an expiry and click Load Chain</div>
          <div className="state-box-sub">
            Optionally enter the current spot price to center the chain around ATM.
          </div>
        </div>
      )}

      {/* Order modal */}
      {modal && (
        <OrderModal
          side={modal.side}
          row={modal.row}
          optType={modal.optType}
          onClose={() => setModal(null)}
          onSuccess={handleOrderSuccess}
        />
      )}
    </div>
  );
}
