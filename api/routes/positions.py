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


async def _call_xts(coro, error_msg: str):
    try:
        data = await coro
        return data
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{error_msg}: {exc}") from exc


@router.get("", response_model=PositionResponse)
async def get_positions(
    xts=Depends(get_xts_interactive),
):
    """Fetch current net positions from XTS."""
    data = await _call_xts(xts.get_positions("NetWise"), "Failed to fetch positions")
    return PositionResponse(data=data)


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
