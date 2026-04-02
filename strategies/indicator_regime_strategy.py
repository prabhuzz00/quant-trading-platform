"""
Indicator-Regime Strategy — regime-aware multi-indicator single-leg strategy.

Data pipeline
-------------
1. OHLCV candles are pre-loaded into :class:`~core.candle_store.CandleStore`
   during startup via :class:`~engine.warmup.WarmupService` (XTS Market Data
   OHLC endpoint) and kept up-to-date by the live
   :class:`~core.market_data_socket.MarketDataSocket`.
2. On every completed bar the strategy fetches the buffered candles, calls
   :class:`~engine.regime_detector.RegimeDetector` to identify the current
   market regime, then selects the appropriate indicator set for that regime
   and generates buy / sell signals.

Indicator mapping per regime
-----------------------------
TRENDING_BULLISH  – MACD bullish crossover confirmed by EMA → BUY
TRENDING_BEARISH  – MACD bearish crossover confirmed by EMA → SELL
SIDEWAYS_LOW_VOL  – RSI + Bollinger Band mean-reversion
                    (RSI < ``rsi_oversold`` and price ≤ lower BB → BUY;
                     RSI > ``rsi_overbought`` and price ≥ upper BB → SELL)
SIDEWAYS_HIGH_VOL – same as SIDEWAYS_LOW_VOL but with tighter RSI thresholds
                    (``rsi_oversold - 5`` / ``rsi_overbought + 5``)
HIGH_VOLATILITY   – ATR breakout: close breaks prior bar's high + ATR factor → BUY;
                    close breaks prior bar's low − ATR factor → SELL
UNKNOWN           – no signal (insufficient data)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import structlog

from engine.regime_detector import RegimeDetector, RegimeType
from engine.signal import OrderMode, Signal, SignalAction
from strategies.base_strategy import BaseStrategy

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# Extra RSI buffer applied in SIDEWAYS_HIGH_VOL regime to require more
# extreme oversold / overbought readings before entering a trade.
_RSI_HIGH_VOL_ADJUSTMENT: float = 5.0


class IndicatorRegimeStrategy(BaseStrategy):
    """
    Regime-aware indicator strategy.

    Selects MACD, RSI/Bollinger-Band, or ATR-breakout signals depending on
    the market regime detected from XTS OHLCV candles.

    Parameters
    ----------
    name:
        Unique strategy identifier.
    exchange_segment:
        XTS exchange segment string (e.g. ``"NSECM"``).
    exchange_instrument_id:
        Numeric instrument ID (e.g. 26000 for NIFTY 50).
    symbol:
        Human-readable symbol label.
    timeframe:
        Candle size in minutes (must match the candle store key).
    ema_period:
        Period for the EMA trend filter used in trending regimes.
    macd_fast / macd_slow / macd_signal:
        MACD parameters.
    bb_period / bb_std:
        Bollinger Band parameters.
    rsi_period / rsi_oversold / rsi_overbought:
        RSI parameters.
    atr_period / atr_breakout_factor:
        ATR parameters for high-volatility breakout mode.
    quantity:
        Order quantity (lots).
    stoploss_points / target_points:
        Bracket order levels.
    enabled:
        Whether the strategy starts enabled.
    """

    description = (
        "Regime-Aware Indicator Strategy — MACD (trending), "
        "RSI + Bollinger Bands (sideways), ATR breakout (high-vol)"
    )

    def __init__(
        self,
        name: str = "indicator_regime",
        exchange_segment: str = "NSECM",
        exchange_instrument_id: int = 26000,
        symbol: str = "NIFTY",
        timeframe: int = 5,
        ema_period: int = 20,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        atr_period: int = 14,
        atr_breakout_factor: float = 1.5,
        quantity: int = 1,
        stoploss_points: float = 50.0,
        target_points: float = 150.0,
        enabled: bool = False,
    ) -> None:
        super().__init__(name=name, enabled=enabled)
        self.exchange_segment = exchange_segment
        self.exchange_instrument_id = exchange_instrument_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.ema_period = ema_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.atr_breakout_factor = atr_breakout_factor
        self.quantity = quantity
        self.stoploss_points = stoploss_points
        self.target_points = target_points

        # Need enough bars for the slowest indicator (MACD slow EMA = 26) plus
        # some buffer so the regime detector also has sufficient data (60 bars).
        self.warmup_required = True
        self.lookback_period = max(macd_slow + macd_signal, bb_period, rsi_period, 60) + 10

        self._position_open = False
        self._detector = RegimeDetector()

    # ------------------------------------------------------------------
    # Warmup / subscription declarations
    # ------------------------------------------------------------------

    def get_warmup_instruments(self) -> List[Dict[str, Any]]:
        return [
            {
                "exchange_segment": self.exchange_segment,
                "exchange_instrument_id": self.exchange_instrument_id,
                "timeframe": self.timeframe,
                "n_candles": self.lookback_period,
            }
        ]

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        return [
            {
                "exchangeSegment": self.exchange_segment,
                "exchangeInstrumentID": self.exchange_instrument_id,
            }
        ]

    # ------------------------------------------------------------------
    # Pure-Python indicator helpers
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
    def _ema_series(values: List[float], period: int) -> List[float]:
        """Return full EMA series (same length as *values*, first period-1 are NaN)."""
        if len(values) < period:
            return [float("nan")] * len(values)
        k = 2.0 / (period + 1)
        result: List[float] = [float("nan")] * (period - 1)
        seed = sum(values[:period]) / period
        result.append(seed)
        ema = seed
        for v in values[period:]:
            ema = v * k + ema * (1 - k)
            result.append(ema)
        return result

    def _macd(
        self, closes: List[float]
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Return (macd_line, signal_line) for the last bar.

        MACD line  = EMA(fast) − EMA(slow)
        Signal line = EMA(macd_line, signal_period)
        """
        fast_series = self._ema_series(closes, self.macd_fast)
        slow_series = self._ema_series(closes, self.macd_slow)

        macd_series: List[float] = []
        for f, s in zip(fast_series, slow_series):
            if math.isnan(f) or math.isnan(s):
                macd_series.append(float("nan"))
            else:
                macd_series.append(f - s)

        valid = [v for v in macd_series if not math.isnan(v)]
        if len(valid) < self.macd_signal:
            return None, None

        signal_line = self._ema(valid, self.macd_signal)
        macd_line = macd_series[-1] if not math.isnan(macd_series[-1]) else None
        return macd_line, signal_line

    def _prev_macd(self, closes: List[float]) -> tuple[Optional[float], Optional[float]]:
        """Return (macd_line, signal_line) for the bar *before* the last bar."""
        return self._macd(closes[:-1])

    @staticmethod
    def _bollinger(
        closes: List[float], period: int, num_std: float
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """Return (upper, middle, lower) Bollinger Bands."""
        if len(closes) < period:
            return None, None, None
        window = closes[-period:]
        mid = sum(window) / period
        variance = sum((x - mid) ** 2 for x in window) / period
        std = math.sqrt(variance)
        return mid + num_std * std, mid, mid - num_std * std

    @staticmethod
    def _rsi(closes: List[float], period: int) -> Optional[float]:
        """Wilder-smoothed RSI."""
        if len(closes) < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        if len(gains) < period:
            return None
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for g, l in zip(gains[period:], losses[period:]):
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _atr(
        highs: List[float], lows: List[float], closes: List[float], period: int
    ) -> Optional[float]:
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
        atr = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr = (atr * (period - 1) + tr) / period
        return atr

    # ------------------------------------------------------------------
    # Regime-specific signal logic
    # ------------------------------------------------------------------

    def _signal_trending(
        self,
        closes: List[float],
        regime_type: RegimeType,
    ) -> Optional[SignalAction]:
        """MACD crossover with EMA trend filter."""
        macd_now, sig_now = self._macd(closes)
        macd_prev, sig_prev = self._prev_macd(closes)
        ema_val = self._ema(closes, self.ema_period)

        if None in (macd_now, sig_now, macd_prev, sig_prev, ema_val):
            return None

        last_close = closes[-1]
        bullish_cross = macd_prev < sig_prev and macd_now > sig_now  # type: ignore[operator]
        bearish_cross = macd_prev > sig_prev and macd_now < sig_now  # type: ignore[operator]

        if regime_type == RegimeType.TRENDING_BULLISH:
            if bullish_cross and last_close > ema_val:
                return SignalAction.BUY
        elif regime_type == RegimeType.TRENDING_BEARISH:
            if bearish_cross and last_close < ema_val:
                return SignalAction.SELL
        return None

    def _signal_sideways(
        self,
        closes: List[float],
        high_vol: bool,
    ) -> Optional[SignalAction]:
        """RSI + Bollinger Band mean-reversion; tighter thresholds for high-vol sideways."""
        rsi = self._rsi(closes, self.rsi_period)
        upper, _mid, lower = self._bollinger(closes, self.bb_period, self.bb_std)

        if rsi is None or upper is None or lower is None:
            return None

        last_close = closes[-1]
        oversold = self.rsi_oversold - (_RSI_HIGH_VOL_ADJUSTMENT if high_vol else 0.0)
        overbought = self.rsi_overbought + (_RSI_HIGH_VOL_ADJUSTMENT if high_vol else 0.0)

        if rsi < oversold and last_close <= lower:
            return SignalAction.BUY
        if rsi > overbought and last_close >= upper:
            return SignalAction.SELL
        return None

    def _signal_high_vol(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
    ) -> Optional[SignalAction]:
        """ATR-based breakout: price must clear prior bar's extreme by an ATR multiple."""
        atr = self._atr(highs, lows, closes, self.atr_period)
        if atr is None or len(highs) < 2:
            return None

        last_close = closes[-1]
        prev_high = highs[-2]
        prev_low = lows[-2]

        if last_close > prev_high + self.atr_breakout_factor * atr:
            return SignalAction.BUY
        if last_close < prev_low - self.atr_breakout_factor * atr:
            return SignalAction.SELL
        return None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        return []

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []
        if self.candle_store is None:
            logger.warning(
                "IndicatorRegimeStrategy: candle_store not injected", name=self.name
            )
            return []
        if not self.candle_store.is_warmed_up(
            self.exchange_instrument_id, self.timeframe, self.lookback_period
        ):
            logger.debug(
                "IndicatorRegimeStrategy: waiting for warmup",
                name=self.name,
                current=self.candle_store.candle_count(
                    self.exchange_instrument_id, self.timeframe
                ),
                required=self.lookback_period,
            )
            return []

        # --- 1. Fetch OHLCV from CandleStore (populated via XTS Market Data API) ---
        candles = self.candle_store.get_candles(
            self.exchange_instrument_id, self.timeframe
        )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        # --- 2. Detect current market regime ---
        regime = self._detector.detect(candles)
        regime_type = regime.regime_type

        if regime_type == RegimeType.UNKNOWN:
            return []

        # --- 3. Select indicators based on regime and generate signal ---
        action: Optional[SignalAction] = None

        if regime_type in (RegimeType.TRENDING_BULLISH, RegimeType.TRENDING_BEARISH):
            action = self._signal_trending(closes, regime_type)

        elif regime_type in (RegimeType.SIDEWAYS_LOW_VOL, RegimeType.SIDEWAYS_HIGH_VOL):
            action = self._signal_sideways(
                closes, high_vol=(regime_type == RegimeType.SIDEWAYS_HIGH_VOL)
            )

        elif regime_type == RegimeType.HIGH_VOLATILITY:
            action = self._signal_high_vol(highs, lows, closes)

        if action is None:
            return []

        last_close = closes[-1]
        signal = Signal(
            strategy_name=self.name,
            action=action,
            exchange_segment=self.exchange_segment,
            exchange_instrument_id=self.exchange_instrument_id,
            symbol=self.symbol,
            quantity=self.quantity,
            order_mode=OrderMode.BRACKET,
            limit_price=last_close,
            stoploss_points=self.stoploss_points,
            target_points=self.target_points,
            reason=(
                f"Regime={regime_type.value} | "
                f"Indicator={'MACD' if regime_type in (RegimeType.TRENDING_BULLISH, RegimeType.TRENDING_BEARISH) else 'RSI+BB' if regime_type in (RegimeType.SIDEWAYS_LOW_VOL, RegimeType.SIDEWAYS_HIGH_VOL) else 'ATR'} | "
                f"action={action.value} | close={last_close:.2f}"
            ),
        )
        self._position_open = True
        logger.info(
            "IndicatorRegimeStrategy: signal generated",
            action=action.value,
            regime=regime_type.value,
            symbol=self.symbol,
            close=last_close,
        )
        return [signal]

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        # TODO: distinguish entry vs exit fills for accurate position tracking;
        # this simple flag mirrors the pattern used by other strategies and
        # is intentionally conservative (no re-entry after any fill).
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Cancelled", "REJECTED", "Rejected"):
            self._position_open = False
