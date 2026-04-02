import React, { useState, useEffect, useRef, useCallback } from 'react';
import OpenTrades from './OpenTrades';
import ClosedTrades from './ClosedTrades';
import RiskPanel from './RiskPanel';
import StrategyControls from './StrategyControls';
import StrategyDetail from './StrategyDetail';
import LivePnL from './LivePnL';
import PositionViewer from './PositionViewer';
import OrderBook from './OrderBook';
import ManualTrading from './ManualTrading';
import RegimePanel from './RegimePanel';

const NAV_ITEMS = [
  { id: 'dashboard',   label: 'Dashboard',      icon: '📊' },
  { id: 'manual',      label: 'Manual Trade',   icon: '🎯' },
  { id: 'open',        label: 'Open Trades',     icon: '📈' },
  { id: 'closed',      label: 'Closed Trades',   icon: '📉' },
  { id: 'risk',        label: 'Risk',            icon: '🛡️' },
  { id: 'strategies',  label: 'Strategies',      icon: '⚙️' },
  { id: 'regime',      label: 'AI Regime',       icon: '🤖' },
  { id: 'positions',   label: 'Positions',       icon: '📋' },
  { id: 'orders',      label: 'Orders',          icon: '📒' },
];

function pnlClass(val) {
  if (val == null) return 'pnl-neutral';
  return val >= 0 ? 'pnl-positive' : 'pnl-negative';
}

function fmt(val, decimals = 2) {
  if (val == null || val === undefined) return '—';
  const n = Number(val);
  if (isNaN(n)) return '—';
  return (n >= 0 ? '+' : '') + n.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export default function Dashboard() {
  const [activePage, setActivePage] = useState('dashboard');
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [dashboardData, setDashboardData] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);

  const handleWsMessage = useCallback((data) => {
    setDashboardData(data);
    setWsConnected(true);
  }, []);

  const handleWsError = useCallback(() => {
    setWsConnected(false);
  }, []);

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(
        (process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws') + '/dashboard'
      );
      ws.onopen = () => setWsConnected(true);
      ws.onmessage = (event) => {
        try {
          handleWsMessage(JSON.parse(event.data));
        } catch (e) {
          console.error('WS parse error:', e);
        }
      };
      ws.onerror = () => handleWsError();
      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connect, 3000);
      };
      wsRef.current = ws;
    };
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [handleWsMessage, handleWsError]);

  const dailyPnl = dashboardData?.daily_pnl ?? dashboardData?.pnl?.daily_realized ?? null;
  const availableMargin = dashboardData?.risk_metrics?.available_margin ?? null;
  const usedMargin = dashboardData?.risk_metrics?.margin_used ?? null;

  function renderContent() {
    switch (activePage) {
      case 'dashboard':   return <LivePnL dashboardData={dashboardData} />;
      case 'manual':      return <ManualTrading />;
      case 'open':        return <OpenTrades />;
      case 'closed':      return <ClosedTrades />;
      case 'risk':        return <RiskPanel />;
      case 'strategies':
        return selectedStrategy
          ? <StrategyDetail
              strategyName={selectedStrategy.name}
              strategyInfo={selectedStrategy}
              onBack={() => setSelectedStrategy(null)}
            />
          : <StrategyControls onSelectStrategy={setSelectedStrategy} />;
      case 'regime':      return <RegimePanel />;
      case 'positions':   return <PositionViewer />;
      case 'orders':      return <OrderBook />;
      default:            return <LivePnL dashboardData={dashboardData} />;
    }
  }

  const activeLabel = selectedStrategy && activePage === 'strategies'
    ? selectedStrategy.name
    : NAV_ITEMS.find(n => n.id === activePage)?.label || 'Dashboard';

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">Q</div>
          <div>
            <div className="sidebar-logo-text">QuantTrader</div>
            <div className="sidebar-logo-sub">Algo Platform</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Navigation</div>
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              className={`nav-item${activePage === item.id ? ' active' : ''}`}
              onClick={() => {
                setActivePage(item.id);
                if (item.id !== 'strategies') setSelectedStrategy(null);
              }}
            >
              <span className="nav-item-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main Area */}
      <div className="main-area">
        {/* Top Bar */}
        <header className="topbar">
          <span className="topbar-title">{activeLabel}</span>

          {dailyPnl != null && (
            <span>
              <span className="topbar-label">Daily PnL</span>
              <span className={`topbar-pnl ${pnlClass(dailyPnl)}`}>
                ₹{fmt(dailyPnl)}
              </span>
            </span>
          )}

          {availableMargin != null && (
            <span>
              <span className="topbar-label">Avail. Margin</span>
              <span className="topbar-pnl pnl-neutral">
                ₹{Number(availableMargin).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </span>
          )}

          {usedMargin != null && (
            <span>
              <span className="topbar-label">Used Margin</span>
              <span className="topbar-pnl pnl-neutral">
                ₹{Number(usedMargin).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </span>
          )}

          <div className="connection-status">
            <div className="status-dot-group">
              <span className={`status-dot ${wsConnected ? 'connected' : 'disconnected'}`} />
              <span>Market</span>
            </div>
            <div className="status-dot-group">
              <span className={`status-dot ${wsConnected ? 'connected' : 'disconnected'}`} />
              <span>Orders</span>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="content-area">
          {renderContent()}
        </main>
      </div>
    </div>
  );
}
