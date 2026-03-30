"""Manual trading routes: Nifty 50 option chain viewer and order placement."""
import asyncio
import json
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from api.dependencies import get_instrument_manager, get_xts_interactive, get_xts_market_data
from api.schemas import (
    ExpiryListResponse,
    ManualOrderRequest,
    ManualOrderResponse,
    OptionChainResponse,
    OptionChainRow,
)
from engine.instrument_manager import InstrumentManager

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/manual", tags=["manual-trading"])


# ---------------------------------------------------------------------------
# Quote extraction helpers
# ---------------------------------------------------------------------------

def _touchline(quote: Optional[Dict]) -> Dict:
    if not quote:
        return {}
    return quote.get("Touchline") or {}


def _get_ltp(quote: Optional[Dict]) -> Optional[float]:
    v = _touchline(quote).get("LastTradedPrice")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get_bid(quote: Optional[Dict]) -> Optional[float]:
    v = (_touchline(quote).get("BidInfo") or {}).get("Price")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get_ask(quote: Optional[Dict]) -> Optional[float]:
    v = (_touchline(quote).get("AskInfo") or {}).get("Price")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get_oi(quote: Optional[Dict]) -> Optional[int]:
    v = quote.get("OpenInterest") if quote else None
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get_volume(quote: Optional[Dict]) -> Optional[int]:
    v = _touchline(quote).get("TotalTradedQuantity")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get_change_pct(quote: Optional[Dict]) -> Optional[float]:
    v = _touchline(quote).get("PercentChange")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/expiries", response_model=ExpiryListResponse, summary="List option expiry dates")
async def get_expiries(
    symbol: str = Query("NIFTY", description="Underlying symbol (e.g. NIFTY, BANKNIFTY)"),
    exchange_segment: str = Query("NSEFO", description="Exchange segment"),
    series: str = Query("OPTIDX", description="Instrument series"),
    im: InstrumentManager = Depends(get_instrument_manager),
) -> ExpiryListResponse:
    """Return available option expiry dates for *symbol* from XTS."""
    expiries = await im.get_expiry_dates(symbol, exchange_segment, series)
    if not expiries:
        raise HTTPException(status_code=404, detail=f"No expiry dates found for {symbol}")
    return ExpiryListResponse(symbol=symbol, expiries=expiries)


@router.get("/option-chain", response_model=OptionChainResponse, summary="Fetch Nifty option chain")
async def get_option_chain(
    symbol: str = Query("NIFTY", description="Underlying symbol"),
    expiry: str = Query(..., description="Expiry date string as returned by /manual/expiries"),
    num_strikes: int = Query(10, ge=1, le=30, description="Strikes to show on each side of ATM"),
    exchange_segment: str = Query("NSEFO", description="Exchange segment"),
    market_data=Depends(get_xts_market_data),
    im: InstrumentManager = Depends(get_instrument_manager),
) -> OptionChainResponse:
    """Single-shot option chain fetch (for initial load / fallback)."""
    try:
        snapshot, _ = await _build_chain_snapshot(
            symbol, expiry, num_strikes, exchange_segment, im, market_data
        )
    except Exception as exc:
        logger.error("Option chain build failed", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No option instruments found for {symbol} expiry '{expiry}'. "
                   "Verify the expiry string matches the format from /manual/expiries.",
        )
    return snapshot

    return OptionChainResponse(
        symbol=symbol,
        expiry=expiry,
        exchange_segment=exchange_segment,
        spot_price=spot_price,
        atm_strike=atm_strike,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Shared chain-building helper (used by REST endpoint and WebSocket streamer)
# ---------------------------------------------------------------------------

async def _build_chain_snapshot(
    symbol: str,
    expiry: str,
    num_strikes: int,
    exchange_segment: str,
    im: InstrumentManager,
    market_data,
    strikes_map: Optional[Dict[float, Dict[str, Dict]]] = None,
) -> tuple:
    """Fetch a fresh option chain snapshot.

    On the first call pass ``strikes_map=None``; the instruments are resolved
    from master data and the map is returned so callers can cache and reuse it
    on subsequent calls (only quotes are refetched each tick).

    Returns ``(OptionChainResponse, strikes_map)`` or ``(None, {})`` if no
    instruments are found.
    """
    if strikes_map is None:
        instruments = await im.get_option_chain_instruments(symbol, expiry, exchange_segment)
        if not instruments:
            return None, {}
        strikes_map = {}
        for inst in instruments:
            strike = inst.get("strike_price", 0.0)
            opt_type = inst.get("option_type", "")
            if opt_type not in ("CE", "PE"):
                continue
            if strike not in strikes_map:
                strikes_map[strike] = {}
            strikes_map[strike][opt_type] = inst

    all_strikes = sorted(strikes_map.keys())
    if not all_strikes:
        return None, strikes_map

    spot_price: Optional[float] = await im.get_spot_price(symbol, exchange_segment)

    atm_strike: Optional[float] = None
    if spot_price is not None:
        atm_strike = min(all_strikes, key=lambda s: abs(s - spot_price))
        atm_idx = all_strikes.index(atm_strike)
        lo = max(0, atm_idx - num_strikes)
        hi = min(len(all_strikes), atm_idx + num_strikes + 1)
        visible_strikes = all_strikes[lo:hi]
    else:
        visible_strikes = all_strikes

    instrument_refs: List[Dict] = []
    for strike in visible_strikes:
        for opt_type in ("CE", "PE"):
            inst = strikes_map[strike].get(opt_type)
            if inst:
                instrument_refs.append({
                    "exchangeSegment": exchange_segment,
                    "exchangeInstrumentID": inst["exchange_instrument_id"],
                })

    quotes_map: Dict[int, Dict] = {}
    if instrument_refs:
        try:
            quotes_result = await market_data.get_quotes(instrument_refs)
            for quote_raw in (quotes_result.get("result") or {}).get("listQuotes") or []:
                quote = json.loads(quote_raw) if isinstance(quote_raw, str) else quote_raw
                inst_id = quote.get("ExchangeInstrumentID")
                if inst_id is not None:
                    quotes_map[int(inst_id)] = quote
        except Exception as exc:
            logger.warning("Quote fetch failed", error=str(exc))

    rows: List[OptionChainRow] = []
    for strike in visible_strikes:
        ce_inst = strikes_map[strike].get("CE")
        pe_inst = strikes_map[strike].get("PE")
        ce_quote = quotes_map.get(ce_inst["exchange_instrument_id"]) if ce_inst else None
        pe_quote = quotes_map.get(pe_inst["exchange_instrument_id"]) if pe_inst else None
        rows.append(OptionChainRow(
            strike=strike,
            is_atm=(atm_strike is not None and strike == atm_strike),
            ce_instrument_id=ce_inst["exchange_instrument_id"] if ce_inst else None,
            ce_lot_size=ce_inst.get("lot_size") if ce_inst else None,
            ce_ltp=_get_ltp(ce_quote),
            ce_bid=_get_bid(ce_quote),
            ce_ask=_get_ask(ce_quote),
            ce_oi=_get_oi(ce_quote),
            ce_volume=_get_volume(ce_quote),
            ce_change_pct=_get_change_pct(ce_quote),
            pe_instrument_id=pe_inst["exchange_instrument_id"] if pe_inst else None,
            pe_lot_size=pe_inst.get("lot_size") if pe_inst else None,
            pe_ltp=_get_ltp(pe_quote),
            pe_bid=_get_bid(pe_quote),
            pe_ask=_get_ask(pe_quote),
            pe_oi=_get_oi(pe_quote),
            pe_volume=_get_volume(pe_quote),
            pe_change_pct=_get_change_pct(pe_quote),
        ))

    response = OptionChainResponse(
        symbol=symbol,
        expiry=expiry,
        exchange_segment=exchange_segment,
        spot_price=spot_price,
        atm_strike=atm_strike,
        rows=rows,
    )
    return response, strikes_map


# ---------------------------------------------------------------------------
# Real-time WebSocket streamer
# ---------------------------------------------------------------------------

@router.websocket("/ws/option-chain")
async def option_chain_ws(
    websocket: WebSocket,
    symbol: str = Query("NIFTY"),
    expiry: str = Query(...),
    num_strikes: int = Query(10, ge=1, le=30),
    exchange_segment: str = Query("NSEFO"),
) -> None:
    """Stream live option chain quotes over WebSocket.

    Sends a full ``OptionChainResponse`` JSON snapshot every 2 seconds.
    The ``strikes_map`` (instrument→strike mapping from master data) is
    resolved once on connect and reused every tick — only quotes and spot
    price are re-fetched each cycle.
    """
    await websocket.accept()
    market_data = get_xts_market_data()
    im = get_instrument_manager()

    strikes_map: Optional[Dict] = None

    try:
        while True:
            snapshot, strikes_map = await _build_chain_snapshot(
                symbol, expiry, num_strikes, exchange_segment, im, market_data, strikes_map
            )
            if snapshot is None:
                await websocket.send_text(json.dumps({
                    "error": f"No option instruments found for {symbol} expiry '{expiry}'"
                }))
                break

            await websocket.send_text(snapshot.model_dump_json())
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Option chain WebSocket error", symbol=symbol, error=str(exc))
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass


@router.post("/order", response_model=ManualOrderResponse, summary="Place a manual order")
async def place_manual_order(
    request: ManualOrderRequest,
    xts_interactive=Depends(get_xts_interactive),
) -> ManualOrderResponse:
    """Place a regular order directly via the XTS Interactive API.

    This bypasses automated strategy risk checks.  Basic field validation is
    performed by Pydantic.  The caller is responsible for position sizing.
    """
    order_side = request.order_side.upper()
    if order_side not in ("BUY", "SELL"):
        raise HTTPException(status_code=422, detail="order_side must be BUY or SELL")

    order_type = request.order_type.upper()
    if order_type not in ("MARKET", "LIMIT", "SL", "SL-M"):
        raise HTTPException(status_code=422, detail="order_type must be MARKET, LIMIT, SL, or SL-M")

    product_type = request.product_type.upper()
    if product_type not in ("MIS", "NRML", "CNC"):
        raise HTTPException(status_code=422, detail="product_type must be MIS, NRML, or CNC")

    limit_price = request.limit_price or 0.0
    stop_price = request.stop_price or 0.0

    try:
        result = await xts_interactive.place_order(
            exchange_segment=request.exchange_segment,
            exchange_instrument_id=request.exchange_instrument_id,
            product_type=product_type,
            order_type=order_type,
            order_side=order_side,
            time_in_force=request.time_in_force.upper(),
            disclosed_quantity=0,
            order_quantity=request.quantity,
            limit_price=limit_price,
            stop_price=stop_price,
        )
    except Exception as exc:
        logger.error(
            "Manual order placement failed",
            instrument_id=request.exchange_instrument_id,
            side=order_side,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Order placement failed: {exc}") from exc

    raw_result = result.get("result", {})
    if isinstance(raw_result, dict):
        order_id = str(raw_result.get("AppOrderID") or raw_result.get("appOrderID") or "")
    else:
        order_id = str(raw_result)

    logger.info(
        "Manual order placed",
        order_id=order_id,
        instrument_id=request.exchange_instrument_id,
        side=order_side,
        qty=request.quantity,
    )
    return ManualOrderResponse(order_id=order_id, message="Order placed successfully")
