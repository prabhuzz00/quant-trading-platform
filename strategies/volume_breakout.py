"""
Volume Breakout Strategy – single-leg.

Entry logic:
  * Volume filter : current bar volume > ``volume_multiplier`` × SMA(volume, period).
  * Price filter  : close breaks above the highest high of the last
                    ``price_lookback`` bars (bullish) or below the lowest low
                    (bearish).
  * EMA filter    : close above EMA(ema_period) → long only;
                    close below EMA(ema_period) → short only.

Requires historical candles for Volume SMA and EMA calculation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class VolumeBreakoutStrategy(BaseStrategy):
    """
    Volume Breakout single-leg strategy.

    Fires when a completed bar shows an abnormally high volume coinciding
    with a price breakout above/below a recent high/low, confirmed by EMA
    trend direction.
    """

    description = "Volume Breakout – high-volume price breakout with EMA trend filter"

    def __init__(
        self,
        name: str = "volume_breakout",
        exchange_segment: str = "NSECM",
        exchange_instrument_id: int = 26000,  # NIFTY 50 default
        symbol: str = "NIFTY",
        timeframe: int = 5,            # candle timeframe in minutes
        volume_sma_period: int = 20,
        volume_multiplier: float = 2.0,
        price_lookback: int = 10,
        ema_period: int = 20,
        quantity: int = 1,
        stoploss_points: float = 50.0,
        target_points: float = 150.0,
        enabled: bool = False,
    ):
        super().__init__(name=name, enabled=enabled)
        self.exchange_segment = exchange_segment
        self.exchange_instrument_id = exchange_instrument_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.volume_sma_period = volume_sma_period
        self.volume_multiplier = volume_multiplier
        self.price_lookback = price_lookback
        self.ema_period = ema_period
        self.quantity = quantity
        self.stoploss_points = stoploss_points
        self.target_points = target_points

        # Warmup configuration – need enough bars for both indicators
        self.warmup_required = True
        self.lookback_period = max(volume_sma_period, ema_period, price_lookback) + 5

        self._position_open = False

    # ------------------------------------------------------------------
    # Warmup declaration
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
    # Indicator helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def _ema(closes: List[float], period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        k = 2.0 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        # Volume Breakout relies on completed bars, not individual ticks
        return []

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []
        if self.candle_store is None:
            logger.warning("VolumeBreakoutStrategy: candle_store not injected", name=self.name)
            return []
        if not self.candle_store.is_warmed_up(
            self.exchange_instrument_id, self.timeframe, self.lookback_period
        ):
            logger.debug(
                "VolumeBreakoutStrategy: waiting for warmup",
                name=self.name,
                current=self.candle_store.candle_count(
                    self.exchange_instrument_id, self.timeframe
                ),
                required=self.lookback_period,
            )
            return []

        candles = self.candle_store.get_candles(
            self.exchange_instrument_id, self.timeframe
        )
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        # Indicators (use all but the most-recent bar as history)
        volume_sma = self._sma(volumes[:-1], self.volume_sma_period)
        ema_val = self._ema(closes[:-1], self.ema_period)
        if volume_sma is None or ema_val is None:
            return []

        current_close = closes[-1]
        current_volume = volumes[-1]

        # Volume condition
        if current_volume < self.volume_multiplier * volume_sma:
            return []

        # Price breakout condition
        n = self.price_lookback
        prior_highs = highs[-(n + 1):-1]
        prior_lows = lows[-(n + 1):-1]
        if not prior_highs or not prior_lows:
            return []

        resistance = max(prior_highs)
        support = min(prior_lows)

        action: Optional[SignalAction] = None
        if current_close > resistance and current_close > ema_val:
            action = SignalAction.BUY
        elif current_close < support and current_close < ema_val:
            action = SignalAction.SELL

        if action is None:
            return []

        signal = Signal(
            strategy_name=self.name,
            action=action,
            exchange_segment=self.exchange_segment,
            exchange_instrument_id=self.exchange_instrument_id,
            symbol=self.symbol,
            quantity=self.quantity,
            order_mode=OrderMode.BRACKET,
            limit_price=current_close,
            stoploss_points=self.stoploss_points,
            target_points=self.target_points,
            reason=(
                f"Volume breakout: vol={current_volume:.0f} "
                f"vs sma={volume_sma:.0f}, close={current_close:.2f}, "
                f"ema={ema_val:.2f}"
            ),
        )
        self._position_open = True
        logger.info(
            "Volume Breakout signal",
            action=action,
            symbol=self.symbol,
            close=current_close,
            volume=current_volume,
            volume_sma=volume_sma,
        )
        return [signal]

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        # TODO: distinguish entry vs exit fills for accurate position tracking;
        # this simple flag mirrors the pattern used by other strategies and
        # is intentionally conservative (no re-entry after any fill).
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED", "Rejected"):
            self._position_open = False
