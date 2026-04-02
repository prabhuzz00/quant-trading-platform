"""WebSocket dashboard route: pushes live trading data every second."""
import asyncio
import json
from datetime import datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.dependencies import app_state

router = APIRouter(tags=["dashboard"])
logger = structlog.get_logger(__name__)


async def _fetch_margin() -> dict:
    """Fetch available and used margin from XTS balance API.

    Returns a dict with ``available_margin`` and ``margin_used`` keys (floats or
    None when the data cannot be retrieved).
    """
    xts = app_state.get("xts_interactive")
    if xts is None:
        return {"available_margin": None, "margin_used": None}
    try:
        data = await xts.get_balance()
        result = data.get("result", data) if isinstance(data, dict) else {}
        balance_list = result.get("BalanceList", []) if isinstance(result, dict) else []

        # Prefer the "Net" entry; fall back to the first entry in the list.
        entry = next(
            (b for b in balance_list if b.get("limitName") == "Net"),
            balance_list[0] if balance_list else None,
        )
        if entry:
            available = entry.get("marginAvailable")
            used = entry.get("marginUtilized")
            return {
                "available_margin": float(available) if available is not None else None,
                "margin_used": float(used) if used is not None else None,
            }
    except Exception as exc:
        logger.warning("Failed to fetch margin from XTS balance API", error=str(exc))
    return {"available_margin": None, "margin_used": None}


async def _build_dashboard_payload() -> dict:
    trade_manager = app_state.get("trade_manager")
    risk_manager = app_state.get("risk_manager")
    kill_switch = app_state.get("kill_switch")
    market_socket = app_state.get("market_data_socket")
    order_socket = app_state.get("order_socket")

    open_trades: list = []
    daily_pnl_total: float = 0.0
    per_strategy_pnl: list = []
    risk_metrics: dict = {}

    if trade_manager:
        raw_open = trade_manager.get_open_trades()
        open_trades = [
            {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in t.items()}
            for t in raw_open
        ]
        daily_pnl_total = trade_manager.get_total_pnl()

        # Per-strategy aggregation
        strategy_map: dict = {}
        for trade in raw_open:
            sname = trade.get("strategy_name", "unknown")
            if sname not in strategy_map:
                strategy_map[sname] = {"open_trades": 0, "total_pnl": 0.0}
            strategy_map[sname]["open_trades"] += 1
            strategy_map[sname]["total_pnl"] += trade.get("pnl", 0.0)
        per_strategy_pnl = [
            {"strategy_name": k, **v} for k, v in strategy_map.items()
        ]

    if risk_manager:
        daily_pnl = risk_manager.get_daily_loss()
        open_count = trade_manager.get_open_trade_count() if trade_manager else 0
        margin_data = await _fetch_margin()
        risk_metrics = {
            "daily_pnl": daily_pnl,
            "open_trades_count": open_count,
            "margin_used": margin_data["margin_used"],
            "available_margin": margin_data["available_margin"],
            "trading_enabled": risk_manager.config.trading_enabled,
            "kill_switch_active": kill_switch.is_activated if kill_switch else False,
            "per_strategy_metrics": per_strategy_pnl,
        }

    return {
        "open_trades": open_trades,
        "daily_pnl_total": daily_pnl_total,
        "per_strategy_pnl": per_strategy_pnl,
        "risk_metrics": risk_metrics,
        "market_connected": market_socket.is_connected() if market_socket else False,
        "order_connected": order_socket.is_connected() if order_socket else False,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """Push live dashboard data to the connected WebSocket client every second."""
    await websocket.accept()
    try:
        while True:
            payload = await _build_dashboard_payload()
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
