"""Strategy routes: list, toggle, performance metrics."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_strategy_registry, get_trade_manager
from api.schemas import StrategyPnlMetric, StrategyResponse, StrategyToggleRequest

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=List[StrategyResponse])
async def list_strategies(
    registry=Depends(get_strategy_registry),
):
    """List all registered strategies with their enabled status."""
    strategies = registry.get_all_strategies()
    return [
        StrategyResponse(
            name=s.name,
            enabled=s.enabled,
            description=getattr(s, "description", None),
        )
        for s in strategies
    ]


@router.put("/{name}/toggle", response_model=StrategyResponse)
async def toggle_strategy(
    name: str,
    body: StrategyToggleRequest,
    registry=Depends(get_strategy_registry),
):
    """Enable or disable a specific strategy."""
    try:
        strategy = registry.get_strategy(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    strategy.enabled = body.enabled
    return StrategyResponse(
        name=strategy.name,
        enabled=strategy.enabled,
        description=getattr(strategy, "description", None),
    )


@router.get("/{name}/performance", response_model=StrategyPnlMetric)
async def strategy_performance(
    name: str,
    registry=Depends(get_strategy_registry),
    trade_manager=Depends(get_trade_manager),
):
    """Return PnL metrics for a specific strategy."""
    try:
        registry.get_strategy(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")

    all_trades = trade_manager.get_all_trades()
    strategy_trades = [t for t in all_trades if t.get("strategy_name") == name]
    open_count = sum(1 for t in strategy_trades if t.get("status") == "OPEN")
    total_pnl = sum(t.get("pnl", 0.0) for t in strategy_trades)

    return StrategyPnlMetric(
        strategy_name=name,
        open_trades=open_count,
        total_pnl=total_pnl,
    )
