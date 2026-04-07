"""Trade routes: open/closed trades, square-off operations."""
from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies import get_order_manager, get_trade_manager
from api.schemas import (
    ErrorResponse,
    SquareOffRequest,
    TradeDetailResponse,
    TradeListResponse,
    TradeResponse,
)

router = APIRouter(prefix="/trades", tags=["trades"])
logger = structlog.get_logger(__name__)


def _enrich_trade(trade: dict) -> dict:
    """Attach unrealized_pnl / realized_pnl fields to a raw trade dict."""
    enriched = dict(trade)
    status = enriched.get("status", "")
    pnl = enriched.get("pnl", 0.0)
    enriched["unrealized_pnl"] = pnl if status == "OPEN" else 0.0
    enriched["realized_pnl"] = pnl if status == "CLOSED" else 0.0
    # Provide defaults for fields that may be absent in the in-memory dict
    enriched.setdefault("strategy_name", "Manual")
    enriched.setdefault("action", "BUY")
    enriched.setdefault("quantity", enriched.get("filled_qty", 0))
    enriched.setdefault("exchange_segment", "")
    enriched.setdefault("exchange_instrument_id", 0)
    enriched.setdefault("order_mode", "REGULAR")
    enriched.setdefault("limit_price", 0.0)
    enriched.setdefault("stoploss_points", 0.0)
    enriched.setdefault("target_points", 0.0)
    enriched.setdefault("signal_id", None)
    enriched.setdefault("reason", None)
    # Remove non-serializable raw data
    enriched.pop("raw", None)
    return enriched


@router.get("/open", response_model=TradeListResponse)
async def list_open_trades(
    trade_manager=Depends(get_trade_manager),
):
    """List all currently open trades with unrealized PnL."""
    trades = trade_manager.get_open_trades()
    enriched = [_enrich_trade(t) for t in trades]
    return TradeListResponse(
        trades=[TradeResponse(**t) for t in enriched],
        total=len(enriched),
    )


@router.get("/closed", response_model=TradeListResponse)
async def list_closed_trades(
    request: Request,
    date_filter: Optional[str] = Query(None, alias="date", description="Filter by date YYYY-MM-DD"),
    strategy: Optional[str] = Query(None, description="Filter by strategy name"),
    trade_manager=Depends(get_trade_manager),
):
    """List closed trades with optional date and strategy filters."""
    logger.info("Closed trades request", url=str(request.url))
    all_trades = trade_manager.get_all_trades()
    closed = [t for t in all_trades if t.get("status") == "CLOSED"]

    if date_filter:
        try:
            filter_date = date.fromisoformat(date_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format; use YYYY-MM-DD")
        closed = [
            t for t in closed
            if t.get("created_at") and t["created_at"].date() == filter_date
        ]

    if strategy:
        closed = [t for t in closed if t.get("strategy_name") == strategy]

    enriched = [_enrich_trade(t) for t in closed]
    return TradeListResponse(
        trades=[TradeResponse(**t) for t in enriched],
        total=len(enriched),
    )


@router.get("/{trade_id}", response_model=TradeDetailResponse)
async def get_trade(
    trade_id: str,
    trade_manager=Depends(get_trade_manager),
):
    """Get details of a specific trade."""
    trade = trade_manager.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade '{trade_id}' not found")
    return TradeDetailResponse(**_enrich_trade(trade))


@router.post("/squareoff/{trade_id}")
async def squareoff_trade(
    trade_id: str,
    body: SquareOffRequest = SquareOffRequest(),
    order_manager=Depends(get_order_manager),
):
    """Manually square off a specific trade."""
    success = await order_manager.squareoff_trade(trade_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Trade '{trade_id}' not found or already closed")
    return {"message": f"Trade {trade_id} squared off successfully", "trade_id": trade_id}


@router.post("/squareoff-all")
async def squareoff_all_trades(
    order_manager=Depends(get_order_manager),
):
    """Square off all open trades."""
    count = await order_manager.squareoff_all()
    return {"message": f"Squared off {count} trade(s)", "count": count}
