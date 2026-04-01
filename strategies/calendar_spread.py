from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import inspect
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class CalendarSpread(BaseStrategy):
    """
    Calendar Spread: Sell near-month ATM CE, Buy far-month ATM CE.
    SL: full debit paid. Target: 50% of max profit (estimated as far_ltp - near_ltp).
    """

    def __init__(
        self,
        name: str = "calendar_spread",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        enabled: bool = False,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity

        self._position_open: bool = False
        self._near_ce: Optional[Dict] = None
        self._far_ce: Optional[Dict] = None

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        instruments = []
        if self._near_ce:
            instruments.append(self._near_ce)
        if self._far_ce:
            instruments.append(self._far_ce)
        return instruments

    async def _load_instruments(self, spot_price: float):
        if self.instrument_manager is None:
            return
        near_expiry = await self.instrument_manager.get_nearest_expiry(self.symbol)
        if not near_expiry:
            return

        far_expiry = None
        sig = inspect.signature(self.instrument_manager.get_nearest_expiry)
        if "after" in sig.parameters:
            far_expiry = await self.instrument_manager.get_nearest_expiry(self.symbol, after=near_expiry)
        else:
            logger.warning("Calendar spread: get_nearest_expiry does not support 'after' param, using near expiry for far leg")
            far_expiry = near_expiry

        atm = self.instrument_manager.get_atm_strike(spot_price)

        self._near_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, near_expiry, "CE", atm, self.exchange_segment, "XX"
        )
        self._far_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, far_expiry, "CE", atm, self.exchange_segment, "XX"
        )

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []

        spot_price = data.get("ltp") or data.get("spot_price")
        if not spot_price:
            return []

        if not self._near_ce or not self._far_ce:
            await self._load_instruments(float(spot_price))
            return []

        near_ltp = self.instrument_manager.get_ltp(
            self._near_ce.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None
        far_ltp = self.instrument_manager.get_ltp(
            self._far_ce.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None

        if near_ltp and far_ltp:
            debit = far_ltp - near_ltp
            if debit <= 0:
                return []
            max_profit_est = debit
            target_pts = round(max_profit_est * 0.50, 2)

            signals = [
                Signal(
                    strategy_name=self.name,
                    action=SignalAction.SELL,
                    exchange_segment=self.exchange_segment,
                    exchange_instrument_id=self._near_ce.get("ExchangeInstrumentID", 0),
                    symbol=f"{self.symbol}_NEAR_CE",
                    quantity=self.quantity,
                    order_mode=OrderMode.BRACKET,
                    limit_price=near_ltp,
                    stoploss_points=round(near_ltp * 2, 2),
                    target_points=round(near_ltp, 2),
                    reason="Calendar Spread sell near CE",
                ),
                Signal(
                    strategy_name=self.name,
                    action=SignalAction.BUY,
                    exchange_segment=self.exchange_segment,
                    exchange_instrument_id=self._far_ce.get("ExchangeInstrumentID", 0),
                    symbol=f"{self.symbol}_FAR_CE",
                    quantity=self.quantity,
                    order_mode=OrderMode.BRACKET,
                    limit_price=far_ltp,
                    stoploss_points=round(debit, 2),
                    target_points=round(target_pts, 2),
                    reason="Calendar Spread buy far CE",
                ),
            ]
            self._position_open = True
            logger.info("Calendar spread entry signals generated", symbol=self.symbol, debit=debit)
            return signals

        return []

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            self._position_open = False
