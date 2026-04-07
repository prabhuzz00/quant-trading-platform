"""Backtesting API routes — run strategy backtests and comparisons."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from strategies.catalog import get_all_strategies, get_strategy_by_id
from engine.backtester import run_backtest, BacktestResult

router = APIRouter(prefix="/backtest", tags=["backtesting"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    strategy_id: str = Field(..., description="Strategy ID from catalog")
    spot: float = Field(22000.0, gt=0, description="Initial spot price")
    iv: float = Field(0.15, gt=0, description="Implied volatility (decimal)")
    rate: float = Field(0.07, description="Risk-free rate")
    hold_days: int = Field(7, ge=1, le=60, description="Hold period in days")
    stop_loss_mult: float = Field(2.0, gt=0, description="Stop loss multiplier")
    profit_target_pct: float = Field(0.50, gt=0, le=1.0, description="Profit target fraction")
    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    num_trades: int = Field(52, ge=5, le=500, description="Number of simulated trades")


class TradeResponse(BaseModel):
    trade_id: int
    strategy_id: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    legs: List[Dict[str, Any]]


class EquityCurvePoint(BaseModel):
    date: str
    equity: float
    drawdown: float


class MonthlyPnlPoint(BaseModel):
    month: str
    pnl: float


class BacktestResponse(BaseModel):
    strategy_id: str
    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    max_pnl: float
    min_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    equity_curve: List[EquityCurvePoint]
    monthly_pnl: List[MonthlyPnlPoint]
    trades: List[TradeResponse]
    parameters: Dict[str, Any]


class CompareRequest(BaseModel):
    strategy_ids: Optional[List[str]] = Field(
        None, description="Strategy IDs to compare. If empty, compares all."
    )
    spot: float = Field(22000.0, gt=0)
    iv: float = Field(0.15, gt=0)
    hold_days: int = Field(7, ge=1, le=60)
    num_trades: int = Field(30, ge=5, le=200)


class ComparisonEntry(BaseModel):
    strategy_id: str
    strategy_name: str
    category: str
    win_rate: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    total_trades: int


class CompareResponse(BaseModel):
    rankings: List[ComparisonEntry]
    sort_by: str = "sharpe_ratio"


# ---------------------------------------------------------------------------
# Helper — convert catalog legs to backtester format
# ---------------------------------------------------------------------------

def _catalog_legs_to_config(strategy) -> List[Dict[str, Any]]:
    """Convert catalog LegDef list to backtester legs_config."""
    return [
        {
            "option_type": leg.option_type.value,
            "action": leg.action.value,
            "strike_offset": leg.strike_offset,
            "quantity": leg.quantity_ratio,
        }
        for leg in strategy.legs
    ]


def _run_single(req_params: Dict[str, Any], strategy) -> BacktestResult:
    """Execute a single backtest for a strategy."""
    legs_config = _catalog_legs_to_config(strategy)
    if not legs_config:
        # Strategy without option legs (e.g. cash-futures arbitrage)
        # Use a simple long call as placeholder
        legs_config = [{"option_type": "CE", "action": "BUY", "strike_offset": 0, "quantity": 1}]

    return run_backtest(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        legs_config=legs_config,
        **req_params,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=BacktestResponse)
async def run_strategy_backtest(req: BacktestRequest):
    """Run a Black-Scholes model backtest for a single strategy."""
    strategy = get_strategy_by_id(req.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy '{req.strategy_id}' not found")

    params = {
        "spot": req.spot,
        "iv": req.iv,
        "rate": req.rate,
        "hold_days": req.hold_days,
        "stop_loss_mult": req.stop_loss_mult,
        "profit_target_pct": req.profit_target_pct,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "num_trades": req.num_trades,
    }

    result = _run_single(params, strategy)

    return BacktestResponse(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        total_trades=result.total_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        win_rate=result.win_rate,
        total_pnl=result.total_pnl,
        avg_pnl=result.avg_pnl,
        max_pnl=result.max_pnl,
        min_pnl=result.min_pnl,
        sharpe_ratio=result.sharpe_ratio,
        max_drawdown=result.max_drawdown,
        profit_factor=result.profit_factor,
        equity_curve=[
            EquityCurvePoint(**ec) for ec in result.equity_curve
        ],
        monthly_pnl=[
            MonthlyPnlPoint(**mp) for mp in result.monthly_pnl
        ],
        trades=[
            TradeResponse(
                trade_id=t.trade_id,
                strategy_id=t.strategy_id,
                entry_date=t.entry_date,
                exit_date=t.exit_date,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                pnl=t.pnl,
                pnl_pct=t.pnl_pct,
                exit_reason=t.exit_reason,
                legs=t.legs,
            )
            for t in result.trades
        ],
        parameters=result.parameters,
    )


@router.post("/compare", response_model=CompareResponse)
async def compare_strategies(req: CompareRequest):
    """Compare multiple strategies — ranked by Sharpe ratio."""
    if req.strategy_ids:
        strategies = []
        for sid in req.strategy_ids:
            s = get_strategy_by_id(sid)
            if s:
                strategies.append(s)
        if not strategies:
            raise HTTPException(status_code=404, detail="No valid strategies found")
    else:
        strategies = get_all_strategies()

    params = {
        "spot": req.spot,
        "iv": req.iv,
        "hold_days": req.hold_days,
        "num_trades": req.num_trades,
        "rate": 0.07,
        "stop_loss_mult": 2.0,
        "profit_target_pct": 0.50,
        "start_date": None,
        "end_date": None,
    }

    rankings: List[ComparisonEntry] = []
    for strategy in strategies:
        result = _run_single(params, strategy)
        rankings.append(ComparisonEntry(
            strategy_id=result.strategy_id,
            strategy_name=result.strategy_name,
            category=strategy.category.value,
            win_rate=result.win_rate,
            total_pnl=result.total_pnl,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            total_trades=result.total_trades,
        ))

    # Sort by Sharpe ratio descending
    rankings.sort(key=lambda x: x.sharpe_ratio, reverse=True)

    return CompareResponse(rankings=rankings, sort_by="sharpe_ratio")
