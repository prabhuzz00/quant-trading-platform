"""
SMC (Smart Money Concept) Confluence Strategy – single-leg.

Entry logic (simplified, production-ready skeleton):
  * Trend filter  : price above/below EMA(ema_period).
  * Structure     : recent swing high/low (last ``structure_lookback`` bars).
  * Entry trigger : on_bar() – price taps a demand/supply zone and
                    EMA confirms direction.

Requires historical candles for EMA and structure calculation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class SMCConfluenceStrategy(BaseStrategy):
    """
    SMC Confluence single-leg strategy.

    Subscribes to an underlying instrument (e.g. NIFTY spot/futures) and
    generates BUY / SELL signals when:
      1. Price is trending (close vs EMA).
      2. Price revisits the most recent demand (bullish) or supply (bearish)
         zone identified from the lookback window.
      3. Signal is only generated during Indian market hours.
    """

    description = "SMC Confluence – EMA trend + demand/supply zone re-test"

    def __init__(
        self,
        name: str = "smc_confluence",
        exchange_segment: str = "NSECM",
        exchange_instrument_id: int = 26000,  # NIFTY 50 default
        symbol: str = "NIFTY",
        timeframe: int = 5,           # candle timeframe in minutes
        ema_period: int = 20,
        structure_lookback: int = 10,  # bars used to find swing highs/lows
        quantity: int = 1,
        stoploss_points: float = 50.0,
        target_points: float = 100.0,
        enabled: bool = True,
    ):
        super().__init__(name=name, enabled=enabled)
        self.exchange_segment = exchange_segment
        self.exchange_instrument_id = exchange_instrument_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.ema_period = ema_period
        self.structure_lookback = structure_lookback
        self.quantity = quantity
        self.stoploss_points = stoploss_points
        self.target_points = target_points

        # Warmup configuration
        self.warmup_required = True
        self.lookback_period = max(ema_period * 3, structure_lookback + 5)

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
    def _ema(closes: List[float], period: int) -> Optional[float]:
        """Compute the most-recent EMA value from a list of close prices."""
        if len(closes) < period:
            return None
        k = 2.0 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema

    def _get_signals_from_structure(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        ema_val: float,
        current_close: float,
    ) -> Optional[SignalAction]:
        """
        Return BUY if price is in a demand zone with bullish EMA alignment,
        SELL if price is in a supply zone with bearish EMA alignment,
        or None if no setup is present.
        """
        n = self.structure_lookback
        if len(closes) < n:
            return None

        recent_high = max(highs[-n:])
        recent_low = min(lows[-n:])
        zone_width = (recent_high - recent_low) * 0.15  # 15% band at extremes

        bullish_trend = current_close > ema_val
        bearish_trend = current_close < ema_val

        # Demand zone: price near recent swing low + bullish trend
        if bullish_trend and current_close <= recent_low + zone_width:
            return SignalAction.BUY

        # Supply zone: price near recent swing high + bearish trend
        if bearish_trend and current_close >= recent_high - zone_width:
            return SignalAction.SELL

        return None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        # SMC confluence relies on bars, not individual ticks
        return []

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []
        if self.candle_store is None:
            logger.warning("SMCConfluenceStrategy: candle_store not injected", name=self.name)
            return []
        if not self.candle_store.is_warmed_up(
            self.exchange_instrument_id, self.timeframe, self.lookback_period
        ):
            logger.debug(
                "SMCConfluenceStrategy: waiting for warmup",
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

        ema_val = self._ema(closes, self.ema_period)
        if ema_val is None:
            return []

        current_close = closes[-1]
        action = self._get_signals_from_structure(closes, highs, lows, ema_val, current_close)
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
            reason=f"SMC confluence: EMA={ema_val:.2f}, close={current_close:.2f}",
        )
        self._position_open = True
        logger.info(
            "SMC Confluence signal",
            action=action,
            symbol=self.symbol,
            close=current_close,
            ema=ema_val,
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
