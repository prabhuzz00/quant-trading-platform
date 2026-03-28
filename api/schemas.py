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
# Error schema
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
