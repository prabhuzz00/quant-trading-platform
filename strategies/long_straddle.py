from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class LongStraddle(BaseStrategy):
    """
    Long Straddle: Buy ATM CE + ATM PE. Profits from high volatility.
    SL: 30% of total premium paid. Target: 2x total premium paid.
    """

    def __init__(
        self,
        name: str = "long_straddle",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        sl_pct: float = 0.30,
        target_multiplier: float = 2.0,
        enabled: bool = True,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.sl_pct = sl_pct
        self.target_multiplier = target_multiplier

        self._position_open: bool = False
        self._ce_instrument: Optional[Dict] = None
        self._pe_instrument: Optional[Dict] = None

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        instruments = []
        if self._ce_instrument:
            instruments.append(self._ce_instrument)
        if self._pe_instrument:
            instruments.append(self._pe_instrument)
        return instruments

    async def _load_instruments(self, spot_price: float):
        if self.instrument_manager is None:
            return
        expiry = await self.instrument_manager.get_nearest_expiry(self.symbol)
        if not expiry:
            return
        atm = self.instrument_manager.get_atm_strike(spot_price)
        self._ce_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", atm, self.exchange_segment, "XX"
        )
        self._pe_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "PE", atm, self.exchange_segment, "XX"
        )

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []

        spot_price = data.get("ltp") or data.get("spot_price")
        if not spot_price:
            return []

        if not self._ce_instrument or not self._pe_instrument:
            await self._load_instruments(float(spot_price))
            return []

        signals = []
        ce_ltp = self.instrument_manager.get_ltp(
            self._ce_instrument.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None
        pe_ltp = self.instrument_manager.get_ltp(
            self._pe_instrument.get("ExchangeInstrumentID", 0)
        ) if self.instrument_manager else None

        if ce_ltp and pe_ltp:
            total_premium = ce_ltp + pe_ltp
            sl_pts = round(total_premium * self.sl_pct, 2)
            target_pts = round(total_premium * self.target_multiplier, 2)

            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._ce_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_ATM_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=ce_ltp,
                stoploss_points=sl_pts,
                target_points=target_pts,
                reason="Long Straddle CE leg",
            ))
            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._pe_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_ATM_PE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=pe_ltp,
                stoploss_points=sl_pts,
                target_points=target_pts,
                reason="Long Straddle PE leg",
            ))
            self._position_open = True
            logger.info("Long straddle entry signals generated", symbol=self.symbol, total_premium=total_premium)

        return signals

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            self._position_open = False
