"""Pydantic schemas for API request/response validation."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Trade schemas
# ---------------------------------------------------------------------------

class TradeResponse(BaseModel):
    order_id: str
    signal_id: Optional[str] = None
    strategy_name: str
    symbol: str
    exchange_segment: str
    exchange_instrument_id: int
    action: str
    order_mode: str
    quantity: int
    limit_price: float
    filled_qty: int
    avg_price: float
    stoploss_points: float
    target_points: float
    pnl: float
    status: str
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TradeDetailResponse(TradeResponse):
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None


class TradeListResponse(BaseModel):
    trades: List[TradeResponse]
    total: int


# ---------------------------------------------------------------------------
# Risk schemas
# ---------------------------------------------------------------------------

class RiskConfigResponse(BaseModel):
    max_capital: float
    max_margin_utilization: float
    max_open_trades: int
    max_daily_loss: float
    max_per_strategy_trades: int
    max_per_strategy_capital: float
    max_quantity_per_order: int
    cooldown_seconds: int
    trading_enabled: bool
    allowed_symbols: List[str]
    allowed_segments: List[str]


class RiskConfigUpdateRequest(BaseModel):
    max_capital: Optional[float] = None
    max_margin_utilization: Optional[float] = None
    max_open_trades: Optional[int] = None
    max_daily_loss: Optional[float] = None
    max_per_strategy_trades: Optional[int] = None
    max_per_strategy_capital: Optional[float] = None
    max_quantity_per_order: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    trading_enabled: Optional[bool] = None
    allowed_symbols: Optional[List[str]] = None
    allowed_segments: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Strategy schemas
# ---------------------------------------------------------------------------

class StrategyResponse(BaseModel):
    name: str
    enabled: bool
    description: Optional[str] = None


class StrategyToggleRequest(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# Position / Balance / Order schemas
# ---------------------------------------------------------------------------

class PositionResponse(BaseModel):
    data: Any = None
    message: str = "OK"


class BalanceResponse(BaseModel):
    data: Any = None
    message: str = "OK"


class OrderResponse(BaseModel):
    data: Any = None
    message: str = "OK"


# ---------------------------------------------------------------------------
# Dashboard / WebSocket schema
# ---------------------------------------------------------------------------

class StrategyPnlMetric(BaseModel):
    strategy_name: str
    open_trades: int
    total_pnl: float


class RiskMetrics(BaseModel):
    daily_pnl: float
    open_trades_count: int
    margin_used: Optional[float] = None
    trading_enabled: bool
    kill_switch_active: bool
    per_strategy_metrics: List[StrategyPnlMetric] = Field(default_factory=list)


class DashboardData(BaseModel):
    open_trades: List[Dict[str, Any]] = Field(default_factory=list)
    daily_pnl_total: float = 0.0
    per_strategy_pnl: List[StrategyPnlMetric] = Field(default_factory=list)
    risk_metrics: Optional[RiskMetrics] = None
    market_connected: bool = False
    order_connected: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Square-off schema
# ---------------------------------------------------------------------------

class SquareOffRequest(BaseModel):
    reason: Optional[str] = "Manual square off"


# ---------------------------------------------------------------------------
# Kill-switch schema
# ---------------------------------------------------------------------------

class KillSwitchRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Reason for activating kill switch")


# ---------------------------------------------------------------------------
# Regime schemas
# ---------------------------------------------------------------------------

class StrategyScoreItem(BaseModel):
    strategy_name: str
    score: int
    regime: str
    recommended: bool
    reason: str


class RegimeStatusResponse(BaseModel):
    regime_type: str
    trend: str
    volatility: str
    volume: str
    atr_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    candle_count: int
    description: str
    scores: List[StrategyScoreItem] = Field(default_factory=list)
    enabled_by_regime: List[str] = Field(default_factory=list)
    disabled_by_regime: List[str] = Field(default_factory=list)
    analyzed_at: Optional[datetime] = None
    error: Optional[str] = None
    auto_regime_enabled: bool = False
    score_threshold: int = 80
    interval_minutes: int = 15


class RegimeConfigResponse(BaseModel):
    enabled: bool
    score_threshold: int
    interval_minutes: int
    instrument_id: int
    timeframe: int


class RegimeConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    score_threshold: Optional[int] = None
    interval_minutes: Optional[int] = None
    instrument_id: Optional[int] = None
    timeframe: Optional[int] = None


# ---------------------------------------------------------------------------
# Error schema
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None


# ---------------------------------------------------------------------------
# Manual trading schemas
# ---------------------------------------------------------------------------

class ExpiryListResponse(BaseModel):
    symbol: str
    expiries: List[str]


class OptionChainRow(BaseModel):
    strike: float
    is_atm: bool = False
    # Call side
    ce_instrument_id: Optional[int] = None
    ce_lot_size: Optional[int] = None
    ce_ltp: Optional[float] = None
    ce_bid: Optional[float] = None
    ce_ask: Optional[float] = None
    ce_oi: Optional[int] = None
    ce_volume: Optional[int] = None
    ce_change_pct: Optional[float] = None
    # Put side
    pe_instrument_id: Optional[int] = None
    pe_lot_size: Optional[int] = None
    pe_ltp: Optional[float] = None
    pe_bid: Optional[float] = None
    pe_ask: Optional[float] = None
    pe_oi: Optional[int] = None
    pe_volume: Optional[int] = None
    pe_change_pct: Optional[float] = None


class OptionChainResponse(BaseModel):
    symbol: str
    expiry: str
    exchange_segment: str
    spot_price: Optional[float] = None
    atm_strike: Optional[float] = None
    rows: List[OptionChainRow]


class ManualOrderRequest(BaseModel):
    exchange_segment: str = Field("NSEFO", description="Exchange segment, e.g. NSEFO")
    exchange_instrument_id: int = Field(..., description="XTS instrument ID from the option chain")
    order_side: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0, description="Order quantity (absolute shares/contracts, not lots)")
    product_type: str = Field("MIS", description="MIS or NRML")
    order_type: str = Field("LIMIT", description="MARKET, LIMIT, SL, or SL-M")
    time_in_force: str = Field("DAY", description="DAY or IOC")
    limit_price: Optional[float] = Field(None, description="Limit price (required for LIMIT / SL orders)")
    stop_price: Optional[float] = Field(None, description="Stop-loss trigger price (required for SL / SL-M orders)")


class ManualOrderResponse(BaseModel):
    order_id: str
    message: str
