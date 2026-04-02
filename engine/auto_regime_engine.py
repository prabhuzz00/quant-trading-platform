"""
Auto-Regime Engine — background task that periodically detects the current
market regime and auto-toggles strategies whose fitness score meets the
configured threshold.

Lifecycle
---------
* Instantiate once during application startup.
* Call :meth:`start` to launch the background loop (returns immediately).
* Call :meth:`stop` during shutdown to cancel the loop.
* Call :meth:`analyze_and_apply` at any time to run a one-shot analysis
  (also used by the manual "Run Analysis" API endpoint).

Configuration (mutable at runtime)
-----------------------------------
enabled:            bool  — when False, loop runs but does not toggle strategies.
interval_minutes:   int   — how often the loop fires.
score_threshold:    int   — minimum score (0-100) to enable a strategy.
instrument_id:      int   — candle-store instrument to read candles from.
timeframe:          int   — candle timeframe in minutes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from core.candle_store import Candle, CandleStore
from core.ohlcv_service import OHLCVService
from engine.regime_detector import MarketRegime, RegimeDetector, RegimeType
from engine.regime_scorer import RegimeScorer, StrategyScore
from strategies.strategy_registry import StrategyRegistry

logger = structlog.get_logger(__name__)


@dataclass
class RegimeAnalysisResult:
    """Result of one regime analysis cycle."""

    regime: MarketRegime
    scores: List[StrategyScore]
    enabled_by_regime: List[str]   # strategies turned ON
    disabled_by_regime: List[str]  # strategies turned OFF
    skipped: List[str]             # strategies not modified (auto-regime disabled)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


class AutoRegimeEngine:
    """
    Orchestrates regime detection → strategy scoring → auto-toggle.

    Parameters
    ----------
    strategy_registry:
        Live registry of all registered strategies.
    candle_store:
        Shared candle buffer populated by the market-data socket.
    instrument_id:
        Instrument to read candles from (default: 26000 = NIFTY 50).
    timeframe:
        Candle timeframe in minutes (default: 5).
    enabled:
        Whether the engine should actually toggle strategies (default: False).
    interval_minutes:
        How often to run in background mode (default: 15).
    score_threshold:
        Minimum score to auto-enable a strategy (default: 80).
    """

    def __init__(
        self,
        strategy_registry: StrategyRegistry,
        candle_store: CandleStore,
        instrument_id: int = 26000,
        timeframe: int = 5,
        enabled: bool = False,
        interval_minutes: int = 15,
        score_threshold: int = 80,
    ) -> None:
        self._registry = strategy_registry
        self._candle_store = candle_store
        self.instrument_id = instrument_id
        self.timeframe = timeframe
        self.enabled = enabled
        self.interval_minutes = interval_minutes
        self.score_threshold = score_threshold

        self._detector = RegimeDetector()
        self._scorer = RegimeScorer(threshold=score_threshold)
        self._last_result: Optional[RegimeAnalysisResult] = None
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def last_result(self) -> Optional[RegimeAnalysisResult]:
        """Last analysis result (None if never run)."""
        return self._last_result

    async def analyze_and_apply(self) -> RegimeAnalysisResult:
        """
        Run one regime analysis cycle.

        1. Fetch candles from the candle store (in-memory).
        2. If insufficient candles, fall back to stored OHLCV data in
           PostgreSQL to avoid the "Insufficient candle data" error.
        3. Detect the current market regime.
        4. Score every registered strategy.
        5. If ``self.enabled`` is True, toggle strategies accordingly.

        Returns the :class:`RegimeAnalysisResult`.
        """
        try:
            candles = self._candle_store.get_candles(self.instrument_id, self.timeframe)

            # Fall back to PostgreSQL OHLCV data when the in-memory buffer
            # does not have enough candles for reliable regime detection.
            if len(candles) < self._detector.min_candles:
                logger.info(
                    "AutoRegimeEngine: in-memory candles insufficient, "
                    "falling back to stored OHLCV data",
                    have=len(candles),
                    need=self._detector.min_candles,
                    instrument_id=self.instrument_id,
                    timeframe=self.timeframe,
                )
                db_candles = await self._fetch_candles_from_db()
                if db_candles:
                    candles = db_candles
                    # Back-fill the in-memory store so subsequent cycles
                    # can skip the DB round-trip.
                    for c in candles:
                        self._candle_store.add_candle(
                            self.instrument_id, self.timeframe, c
                        )
                    logger.info(
                        "AutoRegimeEngine: loaded candles from OHLCV DB",
                        count=len(candles),
                    )

            regime = self._detector.detect(candles)

            strategy_names = [s.name for s in self._registry.get_all_strategies()]
            # Rebuild scorer in case threshold changed at runtime
            self._scorer = RegimeScorer(threshold=self.score_threshold)
            scores = self._scorer.score_strategies(regime, strategy_names)

            enabled_by_regime: List[str] = []
            disabled_by_regime: List[str] = []
            skipped: List[str] = []

            if self.enabled and regime.regime_type != RegimeType.UNKNOWN:
                for score_item in scores:
                    try:
                        strategy = self._registry.get_strategy(score_item.strategy_name)
                    except KeyError:
                        continue

                    should_enable = score_item.recommended
                    if strategy.enabled != should_enable:
                        strategy.enabled = should_enable
                        if should_enable:
                            enabled_by_regime.append(score_item.strategy_name)
                            logger.info(
                                "AutoRegimeEngine: strategy enabled",
                                name=score_item.strategy_name,
                                score=score_item.score,
                                regime=regime.regime_type.value,
                            )
                        else:
                            disabled_by_regime.append(score_item.strategy_name)
                            logger.info(
                                "AutoRegimeEngine: strategy disabled",
                                name=score_item.strategy_name,
                                score=score_item.score,
                                regime=regime.regime_type.value,
                            )
            else:
                skipped = strategy_names

            result = RegimeAnalysisResult(
                regime=regime,
                scores=scores,
                enabled_by_regime=enabled_by_regime,
                disabled_by_regime=disabled_by_regime,
                skipped=skipped,
            )
            self._last_result = result
            return result

        except Exception as exc:
            logger.error("AutoRegimeEngine: analysis failed", error=str(exc))
            error_result = RegimeAnalysisResult(
                regime=MarketRegime(regime_type=RegimeType.UNKNOWN),
                scores=[],
                enabled_by_regime=[],
                disabled_by_regime=[],
                skipped=[],
                error=str(exc),
            )
            self._last_result = error_result
            return error_result

    async def start(self) -> None:
        """Start the background analysis loop."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="auto_regime_engine")
        logger.info(
            "AutoRegimeEngine: background loop started",
            interval_minutes=self.interval_minutes,
            enabled=self.enabled,
        )

    async def stop(self) -> None:
        """Cancel the background loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoRegimeEngine: background loop stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_candles_from_db(self) -> List[Candle]:
        """Query the ``ohlcv_data`` PostgreSQL table for stored candles and
        return them as :class:`Candle` objects ordered oldest → newest.

        This provides a fallback data source when the in-memory
        :class:`CandleStore` has not been warmed up or has fewer candles
        than the regime detector requires.
        """
        try:
            # Request 2× the minimum so indicator warm-up periods (EMA-50,
            # ATR-14, Volume SMA-20) have enough look-back data even when
            # some candles are missing due to non-trading hours or gaps.
            rows = await OHLCVService.get_stored_candles(
                exchange_instrument_id=self.instrument_id,
                timeframe=self.timeframe,
                limit=self._detector.min_candles * 2,
            )
            if not rows:
                logger.debug(
                    "AutoRegimeEngine: no OHLCV rows found in DB",
                    instrument_id=self.instrument_id,
                    timeframe=self.timeframe,
                )
                return []

            # OHLCVService returns rows newest-first; reverse for oldest → newest.
            candles = [
                Candle(
                    timestamp=row.timestamp,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                )
                for row in reversed(rows)
            ]
            return candles
        except Exception as exc:
            logger.warning(
                "AutoRegimeEngine: failed to fetch OHLCV data from DB",
                error=str(exc),
            )
            return []

    async def _loop(self) -> None:
        while True:
            try:
                await self.analyze_and_apply()
            except Exception as exc:
                logger.error("AutoRegimeEngine: loop iteration failed", error=str(exc))
            await asyncio.sleep(self.interval_minutes * 60)
