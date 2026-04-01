from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class CoveredCall(BaseStrategy):
    """
    Covered Call: Sell OTM CE to generate income.
    SL: 2x premium. Target: full premium collected.
    """

    def __init__(
        self,
        name: str = "covered_call",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        otm_points: float = 100.0,
        sl_multiplier: float = 2.0,
        enabled: bool = False,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.otm_points = otm_points
        self.sl_multiplier = sl_multiplier

        self._position_open: bool = False
        self._ce_instrument: Optional[Dict] = None

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        return [self._ce_instrument] if self._ce_instrument else []

    async def _load_instruments(self, spot_price: float):
        if self.instrument_manager is None:
            return
        expiry = await self.instrument_manager.get_nearest_expiry(self.symbol)
        if not expiry:
            return
        ce_strike = self.instrument_manager.get_otm_call_strike(spot_price, self.otm_points)
        self._ce_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", ce_strike, self.exchange_segment, "XX"
        )

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []

        spot_price = data.get("ltp") or data.get("spot_price")
        if not spot_price:
            return []

        if not self._ce_instrument:
            await self._load_instruments(float(spot_price))
            return []

        ce_ltp = self.instrument_manager.get_ltp(
            self._ce_instrument.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None

        if ce_ltp:
            sl_pts = round(ce_ltp * self.sl_multiplier - ce_ltp, 2)
            target_pts = round(ce_ltp, 2)

            signal = Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._ce_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_OTM_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=ce_ltp,
                stoploss_points=sl_pts,
                target_points=target_pts,
                reason="Covered Call sell CE",
            )
            self._position_open = True
            logger.info("Covered call entry signal generated", symbol=self.symbol, ce_ltp=ce_ltp)
            return [signal]

        return []

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            self._position_open = False
