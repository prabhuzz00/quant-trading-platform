"""WarmupService – pre-fetches historical OHLC data into the CandleStore."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Set, Tuple

import structlog

from core.candle_store import Candle, CandleStore
from core.xts_client import XTSMarketDataClient

logger = structlog.get_logger(__name__)

# XTS compressionValue mapping: timeframe (minutes) → compression integer
_TIMEFRAME_TO_COMPRESSION: dict = {
    1: 1,
    3: 3,
    5: 5,
    10: 10,
    15: 15,
    30: 30,
    60: 60,
}

# XTS OHLC startTime / endTime format expected by the API
_XTS_TIME_FMT = "%b %d %Y %H%M%S"


def _parse_ohlc_result(result: Any) -> List[Candle]:
    """
    Parse the ``result`` field of the XTS OHLC response into :class:`Candle`
    objects.

    XTS commonly returns a pipe-separated string of comma-separated fields::

        "1609459200,19000.00,19050.00,18980.00,19020.00,1000000|..."

    Some API versions return a list of dicts with keys
    ``Time``/``Open``/``High``/``Low``/``Close``/``Volume``.
    Both formats are handled here.
    """
    candles: List[Candle] = []

    if isinstance(result, str):
        # Format: "ts|open|high|low|close|vol|oi|,ts|open|..."
        # Candles are comma-separated; fields within each candle are pipe-separated.
        for part in result.split(","):
            part = part.strip().rstrip("|")
            if not part:
                continue
            try:
                fields = part.split("|")
                ts = datetime.fromtimestamp(int(fields[0]), tz=timezone.utc)
                candles.append(
                    Candle(
                        timestamp=ts,
                        open=float(fields[1]),
                        high=float(fields[2]),
                        low=float(fields[3]),
                        close=float(fields[4]),
                        volume=float(fields[5]),
                    )
                )
            except (IndexError, ValueError, OSError) as exc:
                logger.debug("Skipping malformed candle string", data=part, error=str(exc))

    elif isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            try:
                raw_ts = item.get("Time") or item.get("timestamp") or item.get("time", "")
                # Accept both Unix timestamps and ISO strings
                if isinstance(raw_ts, (int, float)):
                    ts = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
                else:
                    ts = datetime.fromisoformat(str(raw_ts))
                candles.append(
                    Candle(
                        timestamp=ts,
                        open=float(item.get("Open", item.get("open", 0))),
                        high=float(item.get("High", item.get("high", 0))),
                        low=float(item.get("Low", item.get("low", 0))),
                        close=float(item.get("Close", item.get("close", 0))),
                        volume=float(item.get("Volume", item.get("volume", 0))),
                    )
                )
            except Exception as exc:
                logger.debug("Skipping malformed candle dict", item=item, error=str(exc))

    return candles


class WarmupService:
    """
    Fetches historical OHLC candles from the XTS API and populates the
    :class:`~core.candle_store.CandleStore`.

    **Production-safety guarantees**

    * Redis fast-path: if a fresh enough cache exists the API is not called.
    * Rate-limiting: the underlying :class:`~core.xts_client.XTSMarketDataClient`
      already enforces 1 req/s on query endpoints.
    * Graceful degradation: individual failures are logged as warnings; a
      partially warmed store still allows strategies to run.
    * Non-blocking: :meth:`warmup_strategies` is awaited **before** the
      :class:`~engine.strategy_engine.StrategyEngine` starts processing ticks,
      but each instrument fetch is done concurrently where possible.
    """

    def __init__(
        self,
        xts_client: XTSMarketDataClient,
        candle_store: CandleStore,
    ) -> None:
        self.xts_client = xts_client
        self.candle_store = candle_store

    async def warmup_instrument(
        self,
        exchange_segment: str,
        instrument_id: int,
        timeframe: int,
        n_candles: int,
    ) -> int:
        """
        Warm up one (instrument, timeframe) pair.

        Returns the number of candles now available in the store.
        """
        # Fast path: Redis cache
        loaded = await self.candle_store.load_from_cache(
            exchange_segment, instrument_id, timeframe
        )
        if loaded and self.candle_store.is_warmed_up(instrument_id, timeframe, n_candles):
            count = self.candle_store.candle_count(instrument_id, timeframe)
            logger.info(
                "Warmup: cache hit",
                instrument_id=instrument_id,
                timeframe=timeframe,
                count=count,
            )
            return count

        # Slow path: XTS OHLC API
        compression = _TIMEFRAME_TO_COMPRESSION.get(timeframe, timeframe)
        end_dt = datetime.now(timezone.utc)
        # Add a 50 % time buffer to account for non-trading hours, weekends,
        # and public holidays – real trading sessions are ~6.25 h/day so a
        # straight lookback_minutes window would fall short.
        lookback_minutes = int(n_candles * timeframe * 1.5)
        start_dt = end_dt - timedelta(minutes=lookback_minutes)

        start_str = start_dt.strftime(_XTS_TIME_FMT)
        end_str = end_dt.strftime(_XTS_TIME_FMT)

        try:
            response = await self.xts_client.get_ohlc(
                exchange_segment=exchange_segment,
                exchange_instrument_id=instrument_id,
                start_time=start_str,
                end_time=end_str,
                compression_value=compression,
            )
            result = response.get("result", {})
            # XTS wraps candle data in result dict under "dataReponse" (broker typo)
            if isinstance(result, dict):
                result = result.get("dataReponse") or result.get("dataResponse", "")
            candles = _parse_ohlc_result(result)

            # Keep only the last n_candles
            for candle in candles[-n_candles:]:
                self.candle_store.add_candle(instrument_id, timeframe, candle)

            count = self.candle_store.candle_count(instrument_id, timeframe)

            # Persist to Redis for the next restart
            await self.candle_store.save_to_cache(
                exchange_segment, instrument_id, timeframe
            )
            logger.info(
                "Warmup: fetched from API",
                instrument_id=instrument_id,
                timeframe=timeframe,
                count=count,
            )
            return count

        except Exception as exc:
            logger.warning(
                "Warmup: failed for instrument",
                instrument_id=instrument_id,
                timeframe=timeframe,
                error=str(exc),
            )
            # Return whatever is already in the store (could be 0)
            return self.candle_store.candle_count(instrument_id, timeframe)

    async def warmup_strategies(self, strategies: List) -> None:
        """
        Iterate over *strategies*, identify those that need historical data,
        and warm up the required (instrument, timeframe) pairs concurrently.

        Each unique (exchange_segment, instrument_id, timeframe) combination
        is fetched only once even if multiple strategies share it.
        """
        seen: Set[Tuple[str, int, int]] = set()
        coros = []

        for strategy in strategies:
            if not getattr(strategy, "warmup_required", False):
                continue
            for spec in strategy.get_warmup_instruments():
                seg: str = spec["exchange_segment"]
                iid: int = spec["exchange_instrument_id"]
                tf: int = spec.get("timeframe", 5)
                n: int = spec.get("n_candles", getattr(strategy, "lookback_period", 50))
                key = (seg, iid, tf)
                if key not in seen:
                    seen.add(key)
                    coros.append(self.warmup_instrument(seg, iid, tf, n))

        if not coros:
            logger.info("No strategies require historical warmup")
            return

        logger.info("Starting historical candle warmup", instruments=len(coros))
        results = await asyncio.gather(*coros, return_exceptions=True)
        success = sum(1 for r in results if isinstance(r, int))
        failures = len(results) - success
        logger.info(
            "Historical candle warmup complete",
            success=success,
            failures=failures,
        )
