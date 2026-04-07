"""Positions routes: proxy calls to XTS interactive client."""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_xts_interactive
from api.schemas import BalanceResponse, OrderResponse, PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])

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


def _normalize_position(pos: dict) -> dict:
    """Normalize a raw XTS position dict into a consistent frontend-friendly shape."""
    return {
        "symbol": pos.get("TradingSymbol", "") or pos.get("symbol", ""),
        "exchange_segment": pos.get("ExchangeSegment", "") or pos.get("exchange_segment", ""),
        "exchange_instrument_id": pos.get("ExchangeInstrumentID", 0) or pos.get("exchange_instrument_id", 0),
        "product_type": pos.get("ProductType", "") or pos.get("product_type", ""),
        "buy_qty": int(pos.get("BuyQuantity", 0) or pos.get("Quantity", 0) or pos.get("buy_qty", 0) or 0),
        "sell_qty": int(pos.get("SellQuantity", 0) or pos.get("sell_qty", 0) or 0),
        "net_qty": int(pos.get("NetQuantity", 0) or pos.get("Quantity", 0) or pos.get("net_qty", 0) or 0),
        "avg_buy_price": float(pos.get("BuyAveragePrice", 0) or pos.get("avg_buy_price", 0) or 0),
        "avg_sell_price": float(pos.get("SellAveragePrice", 0) or pos.get("avg_sell_price", 0) or 0),
        "mtm_pnl": float(
            pos.get("RealizedMTM", 0)
            or pos.get("UnrealizedMTM", 0)
            or pos.get("MTM", 0)
            or pos.get("mtm_pnl", 0)
            or 0
        ),
        "realized_mtm": float(pos.get("RealizedMTM", 0) or pos.get("realized_mtm", 0) or 0),
        "unrealized_mtm": float(pos.get("UnrealizedMTM", 0) or pos.get("unrealized_mtm", 0) or 0),
        "multiplier": float(pos.get("Multiplier", 1) or 1),
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
        # XTS responses may use "result" or "positionList"
        for key in ("result", "positionList"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


@router.get("")
async def get_positions(
    xts=Depends(get_xts_interactive),
):
    """Fetch current net positions from XTS, normalised for the frontend."""
    data = await _call_xts(xts.get_positions("NetWise"), "Failed to fetch positions")
    raw_list = _extract_position_list(data)
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
