from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import structlog

from strategies.base_strategy import BaseStrategy
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class IronCondor(BaseStrategy):
    """
    Iron Condor: Sell OTM CE + PE (strangle) + Buy further OTM CE + PE (wings).
    inner_otm: points OTM for short legs.
    wing_width: additional points for long wings.
    SL: 2x net premium. Target: 50% net premium.
    """

    def __init__(
        self,
        name: str = "iron_condor",
        instrument_manager=None,
        symbol: str = "NIFTY",
        exchange_segment: str = "NSEFO",
        quantity: int = 1,
        inner_otm: float = 100.0,
        wing_width: float = 100.0,
        sl_multiplier: float = 2.0,
        target_pct: float = 0.50,
        enabled: bool = False,
    ):
        super().__init__(name=name, enabled=enabled)
        self.instrument_manager = instrument_manager
        self.symbol = symbol
        self.exchange_segment = exchange_segment
        self.quantity = quantity
        self.inner_otm = inner_otm
        self.wing_width = wing_width
        self.sl_multiplier = sl_multiplier
        self.target_pct = target_pct

        self._position_open: bool = False
        self._short_ce: Optional[Dict] = None
        self._short_pe: Optional[Dict] = None
        self._long_ce: Optional[Dict] = None
        self._long_pe: Optional[Dict] = None

    def _is_within_trading_hours(self) -> bool:
        now = datetime.now(IST)
        return (now.hour, now.minute) >= (9, 20) and (now.hour, now.minute) < (15, 0)

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        return [i for i in [self._short_ce, self._short_pe, self._long_ce, self._long_pe] if i]

    async def _load_instruments(self, spot_price: float):
        if self.instrument_manager is None:
            return
        expiry = await self.instrument_manager.get_nearest_expiry(self.symbol)
        if not expiry:
            return
        short_ce_strike = self.instrument_manager.get_otm_call_strike(spot_price, self.inner_otm)
        short_pe_strike = self.instrument_manager.get_otm_put_strike(spot_price, self.inner_otm)
        long_ce_strike = self.instrument_manager.get_otm_call_strike(spot_price, self.inner_otm + self.wing_width)
        long_pe_strike = self.instrument_manager.get_otm_put_strike(spot_price, self.inner_otm + self.wing_width)

        self._short_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", short_ce_strike, self.exchange_segment, "XX"
        )
        self._short_pe = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "PE", short_pe_strike, self.exchange_segment, "XX"
        )
        self._long_ce = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "CE", long_ce_strike, self.exchange_segment, "XX"
        )
        self._long_pe = await self.instrument_manager.get_option_instrument(
            self.symbol, expiry, "PE", long_pe_strike, self.exchange_segment, "XX"
        )

    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        if not self.enabled or self._position_open:
            return []
        if not self._is_within_trading_hours():
            return []

        spot_price = data.get("ltp") or data.get("spot_price")
        if not spot_price:
            return []

        if not all([self._short_ce, self._short_pe, self._long_ce, self._long_pe]):
            await self._load_instruments(float(spot_price))
            return []

        def get_ltp(inst):
            return self.instrument_manager.get_ltp(inst.get("ExchangeInstrumentID", 0)) if self.instrument_manager else None

        short_ce_ltp = get_ltp(self._short_ce)
        short_pe_ltp = get_ltp(self._short_pe)
        long_ce_ltp = get_ltp(self._long_ce)
        long_pe_ltp = get_ltp(self._long_pe)

        if not all([short_ce_ltp, short_pe_ltp, long_ce_ltp, long_pe_ltp]):
            return []

        net_premium = (short_ce_ltp + short_pe_ltp) - (long_ce_ltp + long_pe_ltp)
        if net_premium <= 0:
            return []

        sl_pts = round(net_premium * self.sl_multiplier, 2)
        target_pts = round(net_premium * self.target_pct, 2)

        signals = [
            Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._short_ce.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_SHORT_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=short_ce_ltp,
                stoploss_points=sl_pts,
                target_points=target_pts,
                reason="Iron Condor short CE",
            ),
            Signal(
                strategy_name=self.name,
                action=SignalAction.SELL,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._short_pe.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_SHORT_PE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=short_pe_ltp,
                stoploss_points=sl_pts,
                target_points=target_pts,
                reason="Iron Condor short PE",
            ),
            Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._long_ce.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_LONG_CE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=long_ce_ltp,
                stoploss_points=round(long_ce_ltp, 2),
                target_points=round(long_ce_ltp * 2, 2),
                reason="Iron Condor long CE wing",
            ),
            Signal(
                strategy_name=self.name,
                action=SignalAction.BUY,
                exchange_segment=self.exchange_segment,
                exchange_instrument_id=self._long_pe.get("ExchangeInstrumentID", 0),
                symbol=f"{self.symbol}_LONG_PE",
                quantity=self.quantity,
                order_mode=OrderMode.BRACKET,
                limit_price=long_pe_ltp,
                stoploss_points=round(long_pe_ltp, 2),
                target_points=round(long_pe_ltp * 2, 2),
                reason="Iron Condor long PE wing",
            ),
        ]
        self._position_open = True
        logger.info("Iron condor entry signals generated", symbol=self.symbol, net_premium=net_premium)
        return signals

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        return await self.on_tick(data)

    async def on_order_update(self, data: Dict[str, Any]) -> None:
        status = data.get("OrderStatus") or data.get("status", "")
        if status in ("Filled", "FILLED"):
            self._position_open = True
        elif status in ("Cancelled", "REJECTED"):
            self._position_open = False
