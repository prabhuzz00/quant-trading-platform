from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class ShortStraddle(BaseStrategy):
    """
    Short Straddle: Sell ATM CE + ATM PE simultaneously.
    Entry: when no position open and within trading hours.
    SL: 50% of premium collected per leg.
    Target: 50% of premium collected per leg.
    """

    def __init__(
        self,
        name: str = "short_straddle",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        sl_pct: float = 0.50,
        target_pct: float = 0.50,
        enabled: bool = False,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.sl_pct = sl_pct
        self.target_pct = target_pct

        self._position_open: bool = False
        self._ce_instrument: Optional[Dict] = None
        self._pe_instrument: Optional[Dict] = None
        self._ce_filled: bool = False
        self._pe_filled: bool = False

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
            ce_sl = ce_ltp * (1 + self.sl_pct)
            ce_target = ce_ltp * (1 - self.target_pct)
            pe_sl = pe_ltp * (1 + self.sl_pct)
            pe_target = pe_ltp * (1 - self.target_pct)

            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._ce_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=ce_ltp,
                stoploss_points=round(ce_sl - ce_ltp, 2),
                target_points=round(ce_ltp - ce_target, 2),
                reason="Short Straddle CE leg",
            ))
            signals.append(Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._pe_instrument.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_PE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=pe_ltp,
                stoploss_points=round(pe_sl - pe_ltp, 2),
                target_points=round(pe_ltp - pe_target, 2),
                reason="Short Straddle PE leg",
            ))
            self._position_open = True
            logger.info("Short straddle entry signals generated", symbol=self.symbol, ce_ltp=ce_ltp, pe_ltp=pe_ltp)

        return signals

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        symbol = data.get("symbol", "")
        if status in ("Filled", "FILLED"):
            if symbol.endswith("_CE") or "CE" in str(data.get("TradingSymbol", "")):
                self._ce_filled = True
            elif symbol.endswith("_PE") or "PE" in str(data.get("TradingSymbol", "")):
                self._pe_filled = True
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            if not (self._ce_filled and self._pe_filled):
                self._position_open = False
