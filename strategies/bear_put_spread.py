from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class BearPutSpread(BaseStrategy):
    """
    Bear Put Spread: Buy higher strike PE (ATM), Sell lower strike PE (ATM - spread_points).
    SL: full debit paid. Target: full spread width minus debit.
    """

    def __init__(
        self,
        name: str = "bear_put_spread",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        spread_points: float = 100.0,
        enabled: bool = True,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.spread_points = spread_points

        self._position_open: bool = False
        self._buy_pe_instrument: Optional[Dict] = None
        self._sell_pe_instrument: Optional[Dict] = None

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        instruments = []
        if self._buy_pe_instrument:
            instruments.append(self._buy_pe_instrument)
        if self._sell_pe_instrument:
            instruments.append(self._sell_pe_instrument)
        return instruments

    async def _load_instruments(self, spot_price: float):
        if self.instrument_manager is None:
            return
        expiry = await self.instrument_manager.get_nearest_expiry(self.symbol)
        if not expiry:
            return
        atm = self.instrument_manager.get_atm_strike(spot_price)
        lower_strike = self.instrument_manager.get_otm_put_strike(spot_price, self.spread_points)
        self._buy_pe_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "PE", atm, self.exchange_segment, "XX"
        )
        self._sell_pe_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "PE", lower_strike, self.exchange_segment, "XX"
        )

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []

        spot_price = data.get("ltp") or data.get("spot_price")
        if not spot_price:
            return []

        if not self._buy_pe_instrument or not self._sell_pe_instrument:
            await self._load_instruments(float(spot_price))
            return []

        signals = []
        buy_ltp = self.instrument_manager.get_ltp(
            self._buy_pe_instrument.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None
        sell_ltp = self.instrument_manager.get_ltp(
            self._sell_pe_instrument.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None

        if buy_ltp and sell_ltp:
            debit = buy_ltp - sell_ltp
            if debit <= 0:
                return []
            target = self.spread_points - debit

            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._buy_pe_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_ATM_PE_BUY",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=buy_ltp,
                stoploss_points=round(debit, 2),
                target_points=round(target, 2),
                reason="Bear Put Spread buy leg",
            ))
            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._sell_pe_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_OTM_PE_SELL",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=sell_ltp,
                stoploss_points=round(sell_ltp * 2, 2),
                target_points=round(sell_ltp, 2),
                reason="Bear Put Spread sell leg",
            ))
            self._position_open = True
            logger.info("Bear put spread entry signals generated", symbol=self.symbol, debit=debit)

        return signals

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            self._position_open = False
