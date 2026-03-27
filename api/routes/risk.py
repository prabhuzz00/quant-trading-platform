"""Risk routes: config CRUD, dashboard metrics, kill-switch control."""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_kill_switch, get_risk_manager, get_trade_manager
from api.schemas import (
    KillSwitchRequest,
    RiskConfigResponse,
    RiskConfigUpdateRequest,
    RiskMetrics,
    StrategyPnlMetric,
)

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/config", response_model=RiskConfigResponse)
async def get_risk_config(
    risk_manager=Depends(get_risk_manager),
):
    """Return the current risk configuration."""
    cfg = risk_manager.config
    return RiskConfigResponse(
        max_capital=cfg.max_capital,
        max_margin_utilization=cfg.max_margin_utilization,
        max_open_trades=cfg.max_open_trades,
        max_daily_loss=cfg.max_daily_loss,
        max_per_strategy_trades=cfg.max_per_strategy_trades,
        max_per_strategy_capital=cfg.max_per_strategy_capital,
        max_quantity_per_order=cfg.max_quantity_per_order,
        cooldown_seconds=cfg.cooldown_seconds,
        trading_enabled=cfg.trading_enabled,
        allowed_symbols=list(cfg.allowed_symbols),
        allowed_segments=list(cfg.allowed_segments),
    )


@router.put("/config", response_model=RiskConfigResponse)
async def update_risk_config(
    body: RiskConfigUpdateRequest,
    risk_manager=Depends(get_risk_manager),
):
    """Update risk configuration fields (only provided fields are changed)."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    risk_manager.update_config(**updates)
    return await get_risk_config(risk_manager=risk_manager)


@router.get("/dashboard", response_model=RiskMetrics)
async def risk_dashboard(
    risk_manager=Depends(get_risk_manager),
    trade_manager=Depends(get_trade_manager),
    kill_switch=Depends(get_kill_switch),
):
    """Return aggregated risk metrics for the dashboard."""
    daily_pnl = risk_manager.get_daily_loss()
    open_trades = trade_manager.get_open_trades()

    # Build per-strategy metrics
    strategy_map: dict = {}
    for trade in open_trades:
        sname = trade.get("strategy_name", "unknown")
        if sname not in strategy_map:
            strategy_map[sname] = {"open_trades": 0, "total_pnl": 0.0}
        strategy_map[sname]["open_trades"] += 1
        strategy_map[sname]["total_pnl"] += trade.get("pnl", 0.0)

    per_strategy = [
        StrategyPnlMetric(strategy_name=k, **v) for k, v in strategy_map.items()
    ]

    return RiskMetrics(
        daily_pnl=daily_pnl,
        open_trades_count=len(open_trades),
        margin_used=None,
        trading_enabled=risk_manager.config.trading_enabled,
        kill_switch_active=kill_switch.is_activated if kill_switch else False,
        per_strategy_metrics=per_strategy,
    )


@router.post("/kill-switch/activate")
async def activate_kill_switch(
    body: KillSwitchRequest,
    kill_switch=Depends(get_kill_switch),
):
    """Activate the kill switch and optionally square off all open positions."""
    if kill_switch is None:
        raise HTTPException(status_code=503, detail="Kill switch not initialized")
    await kill_switch.activate(reason=body.reason, squareoff=True)
    return {"message": "Kill switch activated", "reason": body.reason}


@router.post("/kill-switch/deactivate")
async def deactivate_kill_switch(
    kill_switch=Depends(get_kill_switch),
):
    """Deactivate the kill switch to resume trading."""
    if kill_switch is None:
        raise HTTPException(status_code=503, detail="Kill switch not initialized")
    kill_switch.deactivate()
    return {"message": "Kill switch deactivated"}
