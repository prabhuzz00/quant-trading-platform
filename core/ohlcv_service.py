"""Service for fetching Nifty 50 OHLCV data via the XTS Market Data API and
persisting it to PostgreSQL.

The service re-uses the existing :class:`XTSMarketDataClient` and the candle
parsing logic from :mod:`engine.warmup`.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.xts_client import XTSMarketDataClient
from database.db import get_session
from database.models import OHLCVData

logger = structlog.get_logger(__name__)

# Default Nifty 50 identifiers (NSE Cash segment)
NIFTY50_EXCHANGE_SEGMENT = "NSECM"
NIFTY50_INSTRUMENT_ID = 26000
NIFTY50_SYMBOL = "NIFTY 50"

# XTS OHLC startTime / endTime format expected by the API
_XTS_TIME_FMT = "%b %d %Y %H%M%S"

# XTS compression-value mapping (timeframe minutes → compression in seconds)
# The XTS OHLC API expects compressionValue in seconds (60 = 1-minute candles).
_TIMEFRAME_TO_COMPRESSION: Dict[int, int] = {
    1: 60,
    3: 180,
    5: 300,
    10: 600,
    15: 900,
    30: 1800,
    60: 3600,
}


def _parse_ohlc_result(result: Any) -> List[Dict[str, Any]]:
    """Parse the XTS OHLC ``result`` field into a list of dicts.

    Handles both pipe-separated string format and list-of-dict format returned
    by different XTS API versions.
    """
    candles: List[Dict[str, Any]] = []

    if isinstance(result, str):
        # Format: "ts|open|high|low|close|vol|oi|,ts|open|..."
        # Candles are comma-separated; fields within each candle are pipe-separated.
        for part in result.split(","):
            part = part.strip().rstrip("|")
            if not part:
                continue
            try:
                fields = part.split("|")
                candles.append(
                    {
                        "timestamp": datetime.fromtimestamp(int(fields[0]), tz=timezone.utc),
                        "open": float(fields[1]),
                        "high": float(fields[2]),
                        "low": float(fields[3]),
                        "close": float(fields[4]),
                        "volume": float(fields[5]) if len(fields) > 5 else 0.0,
                    }
                )
            except (IndexError, ValueError, OSError) as exc:
                logger.debug("Skipping malformed candle string", data=part, error=str(exc))

    elif isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            try:
                raw_ts = item.get("Time") or item.get("timestamp") or item.get("time", "")
                if isinstance(raw_ts, (int, float)):
                    ts = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
                else:
                    ts = datetime.fromisoformat(str(raw_ts))
                candles.append(
                    {
                        "timestamp": ts,
                        "open": float(item.get("Open", item.get("open", 0))),
                        "high": float(item.get("High", item.get("high", 0))),
                        "low": float(item.get("Low", item.get("low", 0))),
                        "close": float(item.get("Close", item.get("close", 0))),
                        "volume": float(item.get("Volume", item.get("volume", 0))),
                    }
                )
            except Exception as exc:
                logger.debug("Skipping malformed candle dict", item=item, error=str(exc))

    return candles


class OHLCVService:
    """Fetches OHLCV candle data from the XTS Market Data API and persists it
    to the ``ohlcv_data`` PostgreSQL table.
    """

    def __init__(self, xts_client: XTSMarketDataClient) -> None:
        self.xts_client = xts_client

    async def fetch_and_store(
        self,
        exchange_segment: str = NIFTY50_EXCHANGE_SEGMENT,
        exchange_instrument_id: int = NIFTY50_INSTRUMENT_ID,
        symbol: str = NIFTY50_SYMBOL,
        timeframe: int = 1,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lookback_days: int = 5,
    ) -> int:
        """Fetch OHLCV data from XTS and upsert into PostgreSQL.

        Parameters
        ----------
        exchange_segment:
            XTS exchange segment name (e.g. ``NSECM``).
        exchange_instrument_id:
            XTS numeric instrument identifier (``26000`` for Nifty 50).
        symbol:
            Human-readable symbol stored alongside the data.
        timeframe:
            Candle interval in minutes (1, 5, 15, etc.).
        start_time:
            XTS-formatted start time. If ``None``, computed from *lookback_days*.
        end_time:
            XTS-formatted end time.  If ``None``, defaults to now (UTC).
        lookback_days:
            Number of calendar days to look back when *start_time* is not given.

        Returns
        -------
        int
            Number of candles upserted into the database.
        """
        compression = _TIMEFRAME_TO_COMPRESSION.get(timeframe, timeframe)

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=lookback_days)

        if start_time is None:
            start_time = start_dt.strftime(_XTS_TIME_FMT)
        if end_time is None:
            end_time = end_dt.strftime(_XTS_TIME_FMT)

        # Pass the exchange segment name directly – the OHLC endpoint expects
        # the string name (e.g. "NSECM"), not a numeric segment code.
        logger.info(
            "Fetching OHLCV data from XTS",
            exchange_segment=exchange_segment,
            instrument_id=exchange_instrument_id,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )

        response = await self.xts_client.get_ohlc(
            exchange_segment=exchange_segment,
            exchange_instrument_id=exchange_instrument_id,
            start_time=start_time,
            end_time=end_time,
            compression_value=compression,
        )

        logger.info("XTS OHLC raw response", response=response)
        # XTS wraps data in result dict with a "dataReponse" key (broker typo)
        result_data = response.get("result", {})
        if isinstance(result_data, dict):
            raw_result = result_data.get("dataReponse") or result_data.get("dataResponse", "")
        else:
            raw_result = result_data
        candles = _parse_ohlc_result(raw_result)

        if not candles:
            logger.warning(
                "No OHLCV candles returned from XTS",
                instrument_id=exchange_instrument_id,
            )
            return 0

        # Persist to PostgreSQL using upsert (ON CONFLICT DO UPDATE)
        upserted = await self._upsert_candles(
            exchange_segment=exchange_segment,
            exchange_instrument_id=exchange_instrument_id,
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

        logger.info(
            "OHLCV data saved to PostgreSQL",
            instrument_id=exchange_instrument_id,
            symbol=symbol,
            timeframe=timeframe,
            total_candles=len(candles),
            upserted=upserted,
        )
        return upserted

    async def _upsert_candles(
        self,
        exchange_segment: str,
        exchange_instrument_id: int,
        symbol: str,
        timeframe: int,
        candles: List[Dict[str, Any]],
    ) -> int:
        """Upsert candle rows using PostgreSQL ``ON CONFLICT`` to avoid
        duplicates when re-fetching overlapping time ranges.
        """
        rows = [
            {
                "exchange_segment": exchange_segment,
                "exchange_instrument_id": exchange_instrument_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": c["timestamp"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            }
            for c in candles
        ]

        async with get_session() as session:
            stmt = pg_insert(OHLCVData).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_ohlcv_instrument_tf_ts",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            result = await session.execute(stmt)
            return result.rowcount  # type: ignore[return-value]

    @staticmethod
    async def get_stored_candles(
        exchange_instrument_id: int = NIFTY50_INSTRUMENT_ID,
        symbol: Optional[str] = None,
        timeframe: int = 1,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[OHLCVData]:
        """Retrieve stored OHLCV candles from PostgreSQL.

        Parameters
        ----------
        exchange_instrument_id:
            Filter by instrument ID.
        symbol:
            Optional additional filter by symbol name.
        timeframe:
            Filter by candle timeframe in minutes.
        start_time:
            Only return candles at or after this timestamp.
        end_time:
            Only return candles at or before this timestamp.
        limit:
            Maximum number of rows to return (most recent first).

        Returns
        -------
        list[OHLCVData]
            Matching rows ordered by timestamp descending, capped at *limit*.
        """
        async with get_session() as session:
            query = (
                select(OHLCVData)
                .where(OHLCVData.exchange_instrument_id == exchange_instrument_id)
                .where(OHLCVData.timeframe == timeframe)
            )
            if symbol:
                query = query.where(OHLCVData.symbol == symbol)
            if start_time:
                query = query.where(OHLCVData.timestamp >= start_time)
            if end_time:
                query = query.where(OHLCVData.timestamp <= end_time)

            query = query.order_by(OHLCVData.timestamp.desc()).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())
