from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class ButterflySpread(BaseStrategy):
    """
    Butterfly Spread: Buy 1 lower CE, Sell 2 ATM CE, Buy 1 higher CE.
    wing_width: points from ATM to each wing.
    SL: full debit. Target: wing_width - debit.
    """

    def __init__(
        self,
        name: str = "butterfly_spread",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        wing_width: float = 100.0,
        enabled: bool = True,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.wing_width = wing_width

        self._position_open: bool = False
        self._lower_ce: Optional[Dict] = None
        self._atm_ce: Optional[Dict] = None
        self._upper_ce: Optional[Dict] = None

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        return [i for i in [self._lower_ce, self._atm_ce, self._upper_ce] if i]

    async def _load_instruments(self, spot_price: float):
        if self.instrument_manager is None:
            return
        expiry = await self.instrument_manager.get_nearest_expiry(self.symbol)
        if not expiry:
            return
        atm = self.instrument_manager.get_atm_strike(spot_price)
        lower_strike = self.instrument_manager.get_otm_put_strike(spot_price, self.wing_width)
        upper_strike = self.instrument_manager.get_otm_call_strike(spot_price, self.wing_width)

        self._lower_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", lower_strike, self.exchange_segment, "XX"
        )
        self._atm_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", atm, self.exchange_segment, "XX"
        )
        self._upper_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", upper_strike, self.exchange_segment, "XX"
        )

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []

        spot_price = data.get("ltp") or data.get("spot_price")
        if not spot_price:
            return []

        if not all([self._lower_ce, self._atm_ce, self._upper_ce]):
            await self._load_instruments(float(spot_price))
            return []

        def get_ltp(inst):
            return self.instrument_manager.get_ltp(inst.get("ExchangeInstrumentID", 0)) if self.instrument_manager else None

        lower_ltp = get_ltp(self._lower_ce)
        atm_ltp = get_ltp(self._atm_ce)
        upper_ltp = get_ltp(self._upper_ce)

        if not all([lower_ltp, atm_ltp, upper_ltp]):
            return []

        debit = lower_ltp - (2 * atm_ltp) + upper_ltp
        if debit >= 0:
            return []

        net_debit = abs(debit)
        target = self.wing_width - net_debit

        signals = [
            Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._lower_ce.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_LOWER_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=lower_ltp,
                stoploss_points=round(net_debit, 2),
                target_points=round(max(target, 1.0), 2),
                reason="Butterfly lower wing buy",
            ),
            Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._atm_ce.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_ATM_CE_SELL",
                quantity=self.quantity * 2,
                order_mode=OrderMode.BRACKET,
                limit_price=atm_ltp,
                stoploss_points=round(atm_ltp * 1.5, 2),
                target_points=round(atm_ltp * 0.5, 2),
                reason="Butterfly ATM sell (2x)",
            ),
            Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._upper_ce.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_UPPER_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=upper_ltp,
                stoploss_points=round(net_debit, 2),
                target_points=round(max(target, 1.0), 2),
                reason="Butterfly upper wing buy",
            ),
        ]
        self._position_open = True
        logger.info("Butterfly spread entry signals generated", symbol=self.symbol, net_debit=net_debit)
        return signals

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            self._position_open = False
