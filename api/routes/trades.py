"""Trade routes: open/closed trades, square-off operations."""
from datetime import date, datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies import get_order_manager, get_trade_manager, get_xts_interactive
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


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _trade_from_position(pos: dict) -> dict:
    """Build a trade dict from a raw XTS position with a non-zero net quantity."""
    net_qty = int(pos.get("NetQuantity", 0) or pos.get("Quantity", 0) or 0)
    action = "BUY" if net_qty > 0 else "SELL"
    symbol = pos.get("TradingSymbol", "") or pos.get("symbol", "")
    avg_price = (
        _safe_float(pos.get("BuyAveragePrice")) if net_qty > 0
        else _safe_float(pos.get("SellAveragePrice"))
    )
    unrealized = _safe_float(pos.get("UnrealizedMTM"))
    now = datetime.now(timezone.utc)
    return {
        "order_id": f"POS-{pos.get('ExchangeInstrumentID', symbol)}",
        "signal_id": None,
        "strategy_name": "Broker",
        "symbol": symbol,
        "exchange_segment": pos.get("ExchangeSegment", "") or "",
        "exchange_instrument_id": int(pos.get("ExchangeInstrumentID", 0) or 0),
        "action": action,
        "order_mode": pos.get("ProductType", "REGULAR") or "REGULAR",
        "quantity": abs(net_qty),
        "limit_price": 0.0,
        "filled_qty": abs(net_qty),
        "avg_price": avg_price,
        "stoploss_points": 0.0,
        "target_points": 0.0,
        "pnl": unrealized,
        "unrealized_pnl": unrealized,
        "realized_pnl": 0.0,
        "status": "OPEN",
        "reason": None,
        "created_at": now,
        "updated_at": now,
    }


def _extract_position_list(data) -> list:
    """Extract positions list from various XTS response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, dict):
            pos_list = result.get("positionList")
            if isinstance(pos_list, list):
                return pos_list
        for key in ("result", "positionList"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


@router.get("/open", response_model=TradeListResponse)
async def list_open_trades(
    trade_manager=Depends(get_trade_manager),
    xts=Depends(get_xts_interactive),
):
    """List all currently open trades with unrealized PnL.

    Merges internally tracked trades with live broker positions so that
    trades placed externally (or missed by the order socket) still appear.
    """
    # 1. Internal trades from TradeManager
    trades = trade_manager.get_open_trades()
    enriched = [_enrich_trade(t) for t in trades]
    tracked_symbols = {t.get("symbol") for t in enriched}

    # 2. Live broker positions — add any that are not already tracked
    try:
        raw_data = await xts.get_positions("NetWise")
        positions = _extract_position_list(raw_data)
        for pos in positions:
            net_qty = int(pos.get("NetQuantity", 0) or pos.get("Quantity", 0) or 0)
            symbol = pos.get("TradingSymbol", "") or pos.get("symbol", "")
            if net_qty != 0 and symbol not in tracked_symbols:
                enriched.append(_trade_from_position(pos))
                tracked_symbols.add(symbol)
    except Exception as exc:
        logger.warning("Could not fetch XTS positions for trade merge", error=str(exc))

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
