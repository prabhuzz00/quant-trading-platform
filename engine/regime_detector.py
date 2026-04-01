"""
Market regime detection using pure-Python indicator math.

Regime classification is based on three dimensions derived from OHLCV candles:

  * **Trend**      – relationship between closing price and two EMAs (fast/slow).
  * **Volatility** – Average True Range (ATR) expressed as a percentage of price.
  * **Volume**     – current bar volume relative to a rolling volume SMA.

The five resulting regime types, in order of priority, are:

  HIGH_VOLATILITY    – ATR% is extreme (> ``high_vol_pct``)
  TRENDING_BULLISH   – price > EMA-fast > EMA-slow
  TRENDING_BEARISH   – price < EMA-fast < EMA-slow
  SIDEWAYS_HIGH_VOL  – neutral trend but elevated volatility
  SIDEWAYS_LOW_VOL   – range-bound, quiet market
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import structlog

logger = structlog.get_logger(__name__)


class RegimeType(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    SIDEWAYS_LOW_VOL = "SIDEWAYS_LOW_VOL"
    SIDEWAYS_HIGH_VOL = "SIDEWAYS_HIGH_VOL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass
class MarketRegime:
    """Snapshot of the current market regime."""

    regime_type: RegimeType = RegimeType.UNKNOWN

    # Underlying indicator values (informational)
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    atr_pct: Optional[float] = None          # ATR as % of last close
    volume_ratio: Optional[float] = None     # current vol / vol-SMA

    # Derived trend / volatility labels
    trend: str = "neutral"                   # "bullish" | "bearish" | "neutral"
    volatility: str = "medium"               # "high" | "medium" | "low"
    volume: str = "normal"                   # "high" | "normal" | "low"

    # How many candles were used
    candle_count: int = 0

    # Human-readable description
    description: str = ""


class RegimeDetector:
    """
    Stateless regime detector — call :meth:`detect` with a list of
    :class:`~core.candle_store.Candle` objects and get back a
    :class:`MarketRegime`.

    Parameters
    ----------
    fast_ema_period:
        Period for the fast EMA (default 20).
    slow_ema_period:
        Period for the slow EMA (default 50).
    atr_period:
        Period for ATR calculation (default 14).
    volume_sma_period:
        Period for volume SMA (default 20).
    high_vol_pct:
        ATR-% threshold above which the regime is ``HIGH_VOLATILITY``
        (default 1.5 %).
    low_vol_pct:
        ATR-% threshold below which the regime is ``SIDEWAYS_LOW_VOL``
        (default 0.6 %).
    min_candles:
        Minimum candles required; returns ``UNKNOWN`` if below this
        (default 60).
    """

    def __init__(
        self,
        fast_ema_period: int = 20,
        slow_ema_period: int = 50,
        atr_period: int = 14,
        volume_sma_period: int = 20,
        high_vol_pct: float = 1.5,
        low_vol_pct: float = 0.6,
        min_candles: int = 60,
    ) -> None:
        self.fast_ema_period = fast_ema_period
        self.slow_ema_period = slow_ema_period
        self.atr_period = atr_period
        self.volume_sma_period = volume_sma_period
        self.high_vol_pct = high_vol_pct
        self.low_vol_pct = low_vol_pct
        self.min_candles = min_candles

    # ------------------------------------------------------------------
    # Indicator helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        k = 2.0 / (period + 1)
        ema = values[0]
        for v in values[1:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> Optional[float]:
        """Compute ATR using Wilder's smoothing."""
        if len(closes) < period + 1:
            return None
        trs: List[float] = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        if len(trs) < period:
            return None
        # Simple mean of first ``period`` TRs as seed
        atr = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr = (atr * (period - 1) + tr) / period
        return atr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, candles: list) -> MarketRegime:
        """
        Analyse *candles* and return the current :class:`MarketRegime`.

        Parameters
        ----------
        candles:
            A list of :class:`~core.candle_store.Candle` objects ordered
            oldest → newest.  At least ``self.min_candles`` bars are
            needed for a meaningful result.
        """
        n = len(candles)
        if n < self.min_candles:
            logger.debug(
                "RegimeDetector: insufficient candles",
                have=n,
                need=self.min_candles,
            )
            return MarketRegime(
                regime_type=RegimeType.UNKNOWN,
                candle_count=n,
                description="Insufficient candle data for regime detection.",
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        last_close = closes[-1]

        # --- EMAs ---
        ema_fast = self._ema(closes, self.fast_ema_period)
        ema_slow = self._ema(closes, self.slow_ema_period)

        # --- ATR ---
        atr_val = self._atr(highs, lows, closes, self.atr_period)
        atr_pct: Optional[float] = None
        if atr_val is not None and last_close > 0:
            atr_pct = (atr_val / last_close) * 100.0

        # --- Volume ---
        vol_sma = self._sma(volumes, self.volume_sma_period)
        volume_ratio: Optional[float] = None
        if vol_sma and vol_sma > 0:
            volume_ratio = volumes[-1] / vol_sma

        # --- Classify ---
        trend = "neutral"
        if ema_fast is not None and ema_slow is not None:
            if last_close > ema_fast and ema_fast > ema_slow:
                trend = "bullish"
            elif last_close < ema_fast and ema_fast < ema_slow:
                trend = "bearish"

        volatility = "medium"
        if atr_pct is not None:
            if atr_pct > self.high_vol_pct:
                volatility = "high"
            elif atr_pct < self.low_vol_pct:
                volatility = "low"

        volume_lbl = "normal"
        if volume_ratio is not None:
            if volume_ratio > 1.5:
                volume_lbl = "high"
            elif volume_ratio < 0.75:
                volume_lbl = "low"

        # --- Regime type (priority order) ---
        if volatility == "high":
            regime_type = RegimeType.HIGH_VOLATILITY
        elif trend == "bullish":
            regime_type = RegimeType.TRENDING_BULLISH
        elif trend == "bearish":
            regime_type = RegimeType.TRENDING_BEARISH
        elif volatility == "high":
            regime_type = RegimeType.SIDEWAYS_HIGH_VOL
        elif volatility == "medium" and trend == "neutral":
            # Treat medium volatility in a neutral trend as high-vol sideways
            regime_type = RegimeType.SIDEWAYS_HIGH_VOL
        else:
            regime_type = RegimeType.SIDEWAYS_LOW_VOL

        description = (
            f"Regime: {regime_type.value} | "
            f"Trend: {trend} | "
            f"Volatility: {volatility} ({atr_pct:.2f}% ATR)" if atr_pct is not None
            else f"Regime: {regime_type.value} | Trend: {trend} | Volatility: {volatility}"
        )

        regime = MarketRegime(
            regime_type=regime_type,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            atr_pct=atr_pct,
            volume_ratio=volume_ratio,
            trend=trend,
            volatility=volatility,
            volume=volume_lbl,
            candle_count=n,
            description=description,
        )

        logger.info(
            "RegimeDetector: regime identified",
            regime=regime_type.value,
            trend=trend,
            volatility=volatility,
            atr_pct=round(atr_pct, 3) if atr_pct is not None else None,
            volume_ratio=round(volume_ratio, 2) if volume_ratio is not None else None,
            candles=n,
        )
        return regime
