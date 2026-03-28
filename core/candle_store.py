"""Rolling in-memory candle buffer with optional Redis-backed warm cache."""
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Deque, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Redis cache key prefix for persisted candle buffers
_CACHE_PREFIX = "candles"


@dataclass
class Candle:
    """OHLCV candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleStore:
    """
    Thread-safe (asyncio) rolling candle buffer, keyed by
    (exchange_instrument_id, timeframe_minutes).

    Optionally backed by Redis so the buffer survives short process
    restarts without re-fetching from the exchange API.
    """

    def __init__(
        self,
        redis_client=None,
        cache_ttl: int = 3600,
        max_size: int = 500,
    ) -> None:
        self._data: Dict[Tuple[int, int], Deque[Candle]] = {}
        self._redis = redis_client
        self._cache_ttl = cache_ttl
        self._max_size = max_size

    # ------------------------------------------------------------------
    # Core buffer operations
    # ------------------------------------------------------------------

    def _buf(self, instrument_id: int, timeframe: int) -> Deque[Candle]:
        key = (instrument_id, timeframe)
        if key not in self._data:
            self._data[key] = deque(maxlen=self._max_size)
        return self._data[key]

    def add_candle(self, instrument_id: int, timeframe: int, candle: Candle) -> None:
        """Append a candle to the buffer (oldest candles are evicted when full)."""
        self._buf(instrument_id, timeframe).append(candle)

    def get_candles(
        self, instrument_id: int, timeframe: int, n: Optional[int] = None
    ) -> List[Candle]:
        """Return up to *n* most-recent candles (all if *n* is None)."""
        candles = list(self._buf(instrument_id, timeframe))
        return candles[-n:] if n is not None else candles

    def candle_count(self, instrument_id: int, timeframe: int) -> int:
        return len(self._data.get((instrument_id, timeframe), []))

    def is_warmed_up(
        self, instrument_id: int, timeframe: int, min_candles: int
    ) -> bool:
        return self.candle_count(instrument_id, timeframe) >= min_candles

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _redis_key(exchange_segment: str, instrument_id: int, timeframe: int) -> str:
        return f"{_CACHE_PREFIX}:{exchange_segment}:{instrument_id}:{timeframe}"

    async def load_from_cache(
        self, exchange_segment: str, instrument_id: int, timeframe: int
    ) -> bool:
        """Restore candles from Redis.  Returns True when data was found."""
        if self._redis is None:
            return False
        cache_key = self._redis_key(exchange_segment, instrument_id, timeframe)
        try:
            raw = await self._redis.get(cache_key)
            if not raw:
                return False
            candles_data: List[dict] = json.loads(raw)
            buf = self._buf(instrument_id, timeframe)
            for item in candles_data:
                ts = datetime.fromisoformat(item["timestamp"])
                buf.append(
                    Candle(
                        timestamp=ts,
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(item["volume"]),
                    )
                )
            logger.info(
                "Loaded candles from Redis cache",
                instrument_id=instrument_id,
                timeframe=timeframe,
                count=len(candles_data),
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to load candles from Redis cache",
                instrument_id=instrument_id,
                error=str(exc),
            )
            return False

    async def save_to_cache(
        self, exchange_segment: str, instrument_id: int, timeframe: int
    ) -> None:
        """Persist current buffer to Redis with TTL."""
        if self._redis is None:
            return
        candles = list(self._data.get((instrument_id, timeframe), []))
        if not candles:
            return
        cache_key = self._redis_key(exchange_segment, instrument_id, timeframe)
        try:
            payload = [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ]
            await self._redis.setex(cache_key, self._cache_ttl, json.dumps(payload))
            logger.debug(
                "Saved candles to Redis cache",
                instrument_id=instrument_id,
                timeframe=timeframe,
                count=len(payload),
            )
        except Exception as exc:
            logger.warning(
                "Failed to save candles to Redis cache",
                instrument_id=instrument_id,
                error=str(exc),
            )
