"""WebSocket routes for live data streams."""
import asyncio
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from api.dependencies import get_instrument_manager, get_xts_market_data
from api.routes.manual_trading import (
    _INDEX_INSTRUMENTS,
    _get_ask,
    _get_bid,
    _get_change_pct,
    _get_ltp,
    _get_oi,
    _get_volume,
)
from engine.instrument_manager import InstrumentManager

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])

# How often (seconds) to push a quote refresh to connected clients.
_REFRESH_INTERVAL = 1


def _compute_visible_strikes(
    all_strikes: list,
    spot_price: float | None,
    num_strikes: int,
) -> tuple:
    """Return ``(atm_strike, visible_strikes)`` for the given spot price.

    When *spot_price* is ``None`` the function falls back to the middle of
    *all_strikes* so the first WebSocket message already contains useful data.
    """
    if not all_strikes:
        return None, []

    if spot_price is not None:
        atm = min(all_strikes, key=lambda s: abs(s - spot_price))
        idx = all_strikes.index(atm)
    else:
        atm = None
        idx = len(all_strikes) // 2

    lo = max(0, idx - num_strikes)
    hi = min(len(all_strikes), idx + num_strikes + 1)
    return atm, all_strikes[lo:hi]


@router.websocket("/ws/option-chain")
async def option_chain_ws(
    websocket: WebSocket,
    symbol: str = Query("NIFTY", description="Underlying symbol"),
    expiry: str = Query(..., description="Expiry date string as returned by /api/manual/expiries"),
    num_strikes: int = Query(10, ge=1, le=30, description="Strikes to show on each side of ATM"),
    exchange_segment: str = Query("NSEFO", description="Exchange segment"),
    market_data=Depends(get_xts_market_data),
    im: InstrumentManager = Depends(get_instrument_manager),
) -> None:
    """Stream live option-chain prices for *symbol* / *expiry* every second.

    On each tick the backend:
    1. Fetches the underlying spot price and all visible option quotes in a
       single batched XTS ``get_quotes`` call.
    2. Recomputes the ATM strike and the visible window around it.
    3. Sends a JSON payload that matches the ``OptionChainResponse`` schema.

    The connection is closed by the server only on unrecoverable errors.
    The client may close at any time.
    """
    await websocket.accept()

    # ------------------------------------------------------------------
    # Load the instrument master once (result is cached for 1 hour).
    # ------------------------------------------------------------------
    try:
        instruments = await im.get_option_chain_instruments(symbol, expiry, exchange_segment)
    except Exception as exc:
        logger.error("WS option-chain: master load failed", symbol=symbol, error=str(exc))
        await websocket.send_json({"error": f"Failed to load instruments: {exc}"})
        await websocket.close()
        return

    if not instruments:
        await websocket.send_json(
            {"error": f"No option instruments found for {symbol} expiry '{expiry}'."}
        )
        await websocket.close()
        return

    # Build strikes map: {strike_price: {"CE": inst, "PE": inst}}
    strikes_map: Dict[float, Dict[str, Dict]] = {}
    for inst in instruments:
        strike = inst.get("strike_price", 0.0)
        opt_type = inst.get("option_type", "")
        if opt_type not in ("CE", "PE"):
            continue
        if strike not in strikes_map:
            strikes_map[strike] = {}
        strikes_map[strike][opt_type] = inst

    all_strikes = sorted(strikes_map.keys())

    # Index instrument reference for the underlying spot price.
    index_ref: Optional[Dict] = _INDEX_INSTRUMENTS.get(symbol.upper())

    # ------------------------------------------------------------------
    # Streaming loop
    # ------------------------------------------------------------------
    spot_price: Optional[float] = None

    try:
        while True:
            # ----------------------------------------------------------
            # Determine the visible strike window using the last known
            # spot price (None on the very first iteration).
            # ----------------------------------------------------------
            atm_strike, visible_strikes = _compute_visible_strikes(
                all_strikes, spot_price, num_strikes
            )

            # ----------------------------------------------------------
            # Build a single batch request: index (spot) + visible options.
            # This keeps us within the 1 call/sec XTS rate limit.
            # ----------------------------------------------------------
            option_refs: List[Dict] = []
            for strike in visible_strikes:
                for opt_type in ("CE", "PE"):
                    inst = strikes_map[strike].get(opt_type)
                    if inst:
                        option_refs.append(
                            {
                                "exchangeSegment": exchange_segment,
                                "exchangeInstrumentID": inst["exchange_instrument_id"],
                            }
                        )

            all_refs: List[Dict] = []
            if index_ref:
                all_refs.append(index_ref)
            all_refs.extend(option_refs)

            quotes_map: Dict[int, Dict] = {}
            if all_refs:
                try:
                    result = await market_data.get_quotes(all_refs)
                    for quote in (result.get("result") or {}).get("listQuotes") or []:
                        inst_id = quote.get("ExchangeInstrumentID")
                        if inst_id is None:
                            continue
                        inst_id_int = int(inst_id)
                        # Identify the index quote by its instrument ID.
                        if (
                            index_ref is not None
                            and inst_id_int == index_ref["exchangeInstrumentID"]
                        ):
                            ltp = _get_ltp(quote)
                            if ltp is not None:
                                spot_price = ltp
                        else:
                            quotes_map[inst_id_int] = quote
                except Exception as exc:
                    logger.warning(
                        "WS option-chain: quote fetch failed – sending stale data",
                        error=str(exc),
                    )

            # Recompute ATM and visible window after (possibly) refreshing spot_price.
            atm_strike, visible_strikes = _compute_visible_strikes(
                all_strikes, spot_price, num_strikes
            )

            # ----------------------------------------------------------
            # Build response rows.
            # ----------------------------------------------------------
            rows = []
            for strike in visible_strikes:
                ce_inst = strikes_map[strike].get("CE")
                pe_inst = strikes_map[strike].get("PE")
                ce_quote = quotes_map.get(ce_inst["exchange_instrument_id"]) if ce_inst else None
                pe_quote = quotes_map.get(pe_inst["exchange_instrument_id"]) if pe_inst else None

                rows.append(
                    {
                        "strike": strike,
                        "is_atm": atm_strike is not None and strike == atm_strike,
                        "ce_instrument_id": ce_inst["exchange_instrument_id"] if ce_inst else None,
                        "ce_lot_size": ce_inst.get("lot_size") if ce_inst else None,
                        "ce_ltp": _get_ltp(ce_quote),
                        "ce_bid": _get_bid(ce_quote),
                        "ce_ask": _get_ask(ce_quote),
                        "ce_oi": _get_oi(ce_quote),
                        "ce_volume": _get_volume(ce_quote),
                        "ce_change_pct": _get_change_pct(ce_quote),
                        "pe_instrument_id": pe_inst["exchange_instrument_id"] if pe_inst else None,
                        "pe_lot_size": pe_inst.get("lot_size") if pe_inst else None,
                        "pe_ltp": _get_ltp(pe_quote),
                        "pe_bid": _get_bid(pe_quote),
                        "pe_ask": _get_ask(pe_quote),
                        "pe_oi": _get_oi(pe_quote),
                        "pe_volume": _get_volume(pe_quote),
                        "pe_change_pct": _get_change_pct(pe_quote),
                    }
                )

            payload = {
                "symbol": symbol,
                "expiry": expiry,
                "exchange_segment": exchange_segment,
                "spot_price": spot_price,
                "atm_strike": atm_strike,
                "rows": rows,
            }

            await websocket.send_json(payload)
            await asyncio.sleep(_REFRESH_INTERVAL)

    except WebSocketDisconnect:
        logger.info("WS option-chain: client disconnected", symbol=symbol, expiry=expiry)
    except Exception as exc:
        logger.error("WS option-chain: unhandled error", symbol=symbol, error=str(exc))
        try:
            await websocket.send_json({"error": str(exc)})
            await websocket.close()
        except Exception:
            pass
