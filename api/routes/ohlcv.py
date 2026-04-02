"""API routes for fetching and retrieving OHLCV data."""

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_xts_market_data
from api.schemas import (
    OHLCVFetchRequest,
    OHLCVFetchResponse,
    OHLCVListResponse,
    OHLCVRecord,
)
from core.ohlcv_service import OHLCVService
from core.xts_client import XTSMarketDataClient

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ohlcv", tags=["ohlcv"])


@router.post("/fetch", response_model=OHLCVFetchResponse)
async def fetch_ohlcv(
    body: OHLCVFetchRequest,
    xts_client: XTSMarketDataClient = Depends(get_xts_market_data),
):
    """Fetch OHLCV candle data from the XTS Market Data API and store it in
    PostgreSQL.

    By default fetches Nifty 50 1-minute candles for the last 5 calendar days.
    """
    if not xts_client.token:
        raise HTTPException(
            status_code=503,
            detail="XTS Market Data client is not authenticated. "
                   "Ensure valid API credentials are configured.",
        )

    service = OHLCVService(xts_client)
    try:
        count = await service.fetch_and_store(
            exchange_segment=body.exchange_segment,
            exchange_instrument_id=body.exchange_instrument_id,
            symbol=body.symbol,
            timeframe=body.timeframe,
            start_time=body.start_time,
            end_time=body.end_time,
            lookback_days=body.lookback_days,
        )
    except Exception as exc:
        logger.error("OHLCV fetch failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Failed to fetch OHLCV data: {exc}")

    return OHLCVFetchResponse(
        message=f"Fetched and stored {count} candle(s)",
        candles_upserted=count,
        exchange_segment=body.exchange_segment,
        exchange_instrument_id=body.exchange_instrument_id,
        symbol=body.symbol,
        timeframe=body.timeframe,
    )


@router.get("/data", response_model=OHLCVListResponse)
async def get_ohlcv_data(
    exchange_instrument_id: int = Query(26000, description="Instrument ID (26000 = NIFTY 50)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol name"),
    timeframe: int = Query(1, ge=1, description="Candle interval in minutes"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="End timestamp (ISO 8601)"),
    limit: int = Query(500, ge=1, le=5000, description="Max records to return"),
):
    """Retrieve stored OHLCV data from PostgreSQL.

    Returns records ordered by timestamp descending (newest first).
    """
    try:
        records = await OHLCVService.get_stored_candles(
            exchange_instrument_id=exchange_instrument_id,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Failed to query OHLCV data", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}")

    return OHLCVListResponse(
        records=[OHLCVRecord.model_validate(r) for r in records],
        total=len(records),
    )
