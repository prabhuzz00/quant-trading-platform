"""Positions routes: proxy calls to XTS interactive client."""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_xts_interactive
from api.schemas import BalanceResponse, OrderResponse, PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])


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


@router.get("/orders", response_model=OrderResponse)
async def get_order_book(
    xts=Depends(get_xts_interactive),
):
    """Fetch order book from XTS."""
    data = await _call_xts(xts.get_order_book(), "Failed to fetch order book")
    return OrderResponse(data=data)


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
