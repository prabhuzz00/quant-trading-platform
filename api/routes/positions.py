"""Positions routes: proxy calls to XTS interactive client."""
import structlog
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_xts_interactive
from api.schemas import BalanceResponse, OrderResponse, PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])
logger = structlog.get_logger(__name__)

_XTS_STATUS_MAP = {
    "Filled": "FILLED",
    "PartiallyFilled": "PARTIALFILL",
    "Rejected": "REJECTED",
    "Cancelled": "CANCELLED",
    "New": "PENDING",
    "PendingNew": "PENDING",
    "Placed": "PLACED",
    "Modified": "PENDING",
    "Trigger Pending": "TRIGGER_PENDING",
    "TransactionReceived": "PENDING",
    "CancelledAfterMarketOrder": "CANCELLED",
}


def _normalize_order(order: dict) -> dict:
    status_raw = order.get("OrderStatus", "")
    return {
        "order_id": str(order.get("AppOrderID", "")),
        "exchange_order_id": str(order.get("ExchangeOrderID", "")),
        "symbol": order.get("TradingSymbol", ""),
        "exchange_segment": order.get("ExchangeSegment", ""),
        "exchange_instrument_id": order.get("ExchangeInstrumentID", 0),
        "side": order.get("OrderSide", ""),
        "quantity": order.get("OrderQuantity", 0),
        "filled_qty": order.get("CumulativeQuantity", 0),
        "order_type": order.get("OrderType", ""),
        "product_type": order.get("ProductType", ""),
        "price": float(order.get("OrderPrice", 0) or 0),
        "avg_price": float(order.get("OrderAverageTradedPrice", 0) or 0),
        "status": _XTS_STATUS_MAP.get(status_raw, status_raw.upper() if status_raw else "UNKNOWN"),
        "order_time": order.get("OrderGeneratedDateTime", ""),
        "last_update_time": order.get("LastUpdateTime", ""),
        "reject_reason": order.get("CancelRejectReason", "") or order.get("OtherReason", ""),
    }


def _safe_float(value, default: float = 0.0) -> float:
    """Convert a value to float, handling malformed strings like '0.000.00'."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        s = str(value).strip()
        # Remove all but the first decimal point
        parts = s.split('.')
        if len(parts) > 2:
            s = parts[0] + '.' + ''.join(parts[1:])
        try:
            return float(s)
        except (ValueError, TypeError):
            return default


def _normalize_position(pos: dict) -> dict:
    """Normalize a raw XTS position dict into a consistent frontend-friendly shape."""
    return {
        "symbol": pos.get("TradingSymbol", "") or pos.get("symbol", ""),
        "exchange_segment": pos.get("ExchangeSegment", "") or pos.get("exchange_segment", ""),
        "exchange_instrument_id": pos.get("ExchangeInstrumentID", 0) or pos.get("exchange_instrument_id", 0),
        "product_type": pos.get("ProductType", "") or pos.get("product_type", ""),
        "buy_qty": int(pos.get("BuyQuantity", 0) or pos.get("OpenBuyQuantity", 0) or pos.get("buy_qty", 0) or 0),
        "sell_qty": int(pos.get("SellQuantity", 0) or pos.get("OpenSellQuantity", 0) or pos.get("sell_qty", 0) or 0),
        "open_buy_qty": int(pos.get("OpenBuyQuantity", 0) or 0),
        "open_sell_qty": int(pos.get("OpenSellQuantity", 0) or 0),
        "net_qty": int(pos.get("NetQuantity", 0) or pos.get("Quantity", 0) or pos.get("net_qty", 0) or 0),
        "avg_buy_price": _safe_float(pos.get("BuyAveragePrice") or pos.get("avg_buy_price")),
        "avg_sell_price": _safe_float(pos.get("SellAveragePrice") or pos.get("avg_sell_price")),
        "buy_amount": _safe_float(pos.get("BuyAmount")),
        "sell_amount": _safe_float(pos.get("SellAmount")),
        "net_amount": _safe_float(pos.get("NetAmount")),
        "realized_mtm": _safe_float(pos.get("RealizedMTM") or pos.get("realized_mtm")),
        "unrealized_mtm": _safe_float(pos.get("UnrealizedMTM") or pos.get("unrealized_mtm")),
        "mtm_pnl": _safe_float(pos.get("RealizedMTM")) + _safe_float(pos.get("UnrealizedMTM")) or _safe_float(pos.get("mtm_pnl")),
        "multiplier": _safe_float(pos.get("Multiplier"), default=1.0),
    }


async def _call_xts(coro, error_msg: str):
    try:
        data = await coro
        return data
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{error_msg}: {exc}") from exc


def _extract_position_list(data) -> list:
    """Extract positions list from various XTS response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # XTS wraps positions as: {result: {positionList: [...]}}
        result = data.get("result")
        if isinstance(result, dict):
            pos_list = result.get("positionList")
            if isinstance(pos_list, list):
                return pos_list
        # Flat shapes: {result: [...]} or {positionList: [...]}
        for key in ("result", "positionList"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


@router.get("")
async def get_positions(
    xts=Depends(get_xts_interactive),
):
    """Fetch current net positions from XTS, normalized for the frontend."""
    data = await _call_xts(xts.get_positions("NetWise"), "Failed to fetch positions")
    logger.info("Raw XTS positions response", data=data)
    raw_list = _extract_position_list(data)
    logger.info("Extracted positions list", count=len(raw_list))
    positions = [_normalize_position(p) for p in raw_list]
    return {"positions": positions, "total": len(positions)}


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    xts=Depends(get_xts_interactive),
):
    """Fetch account balance / margin details from XTS."""
    data = await _call_xts(xts.get_balance(), "Failed to fetch balance")
    return BalanceResponse(data=data)


@router.get("/orders")
async def get_order_book(
    xts=Depends(get_xts_interactive),
):
    """Fetch order book from XTS, returning normalized filled/pending/rejected orders."""
    data = await _call_xts(xts.get_order_book(), "Failed to fetch order book")
    raw_list = data.get("result", []) if isinstance(data, dict) else data
    if not isinstance(raw_list, list):
        raw_list = []
    orders = [_normalize_order(o) for o in raw_list]
    return {"orders": orders, "total": len(orders)}


@router.get("/trades", response_model=OrderResponse)
async def get_trade_book(
    xts=Depends(get_xts_interactive),
):
    """Fetch trade book from XTS."""
    data = await _call_xts(xts.get_trade_book(), "Failed to fetch trade book")
    return OrderResponse(data=data)


@router.get("/holdings", response_model=PositionResponse)
async def get_holdings(
    xts=Depends(get_xts_interactive),
):
    """Fetch holdings from XTS."""
    data = await _call_xts(xts.get_holdings(), "Failed to fetch holdings")
    return PositionResponse(data=data)
