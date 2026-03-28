from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class ShortStrangle(BaseStrategy):
    """
    Short Strangle: Sell OTM CE + OTM PE (default 200 points OTM).
    SL: 2x premium per leg. Target: 50% profit per leg.
    """

    def __init__(
        self,
        name: str = "short_strangle",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        otm_points: float = 200.0,
        sl_multiplier: float = 2.0,
        target_pct: float = 0.50,
        enabled: bool = True,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.otm_points = otm_points
        self.sl_multiplier = sl_multiplier
        self.target_pct = target_pct

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
        ce_strike = self.instrument_manager.get_otm_call_strike(spot_price, self.otm_points)
        pe_strike = self.instrument_manager.get_otm_put_strike(spot_price, self.otm_points)
        self._ce_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", ce_strike, self.exchange_segment, "XX"
        )
        self._pe_instrument = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "PE", pe_strike, self.exchange_segment, "XX"
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
            ce_sl = ce_ltp * self.sl_multiplier
            ce_target = ce_ltp * self.target_pct
            pe_sl = pe_ltp * self.sl_multiplier
            pe_target = pe_ltp * self.target_pct

            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._ce_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_OTM_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=ce_ltp,
                stoploss_points=round(ce_sl - ce_ltp, 2),
                target_points=round(ce_target, 2),
                reason="Short Strangle CE leg",
            ))
            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._pe_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_OTM_PE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=pe_ltp,
                stoploss_points=round(pe_sl - pe_ltp, 2),
                target_points=round(pe_target, 2),
                reason="Short Strangle PE leg",
            ))
            self._position_open = True
            logger.info("Short strangle entry signals generated", symbol=self.symbol)

        return signals

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Cancelled", "REJECTED"):
            self._position_open = False
        elif status in ("Filled", "FILLED"):
            self._position_open = True
