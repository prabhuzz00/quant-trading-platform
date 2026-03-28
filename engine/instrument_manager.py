import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
import structlog
from core.xts_client import XTSMarketDataClient

logger = structlog.get_logger(__name__)


class InstrumentManager:
    """Manages option chain, strike selection, expiry dates."""

    def __init__(self, market_client: XTSMarketDataClient):
        self.market_client = market_client
        self._instrument_cache: Dict[str, Dict] = {}
        self._expiry_cache: Dict[str, List[str]] = {}
        self._ltp_cache: Dict[int, float] = {}

    async def get_expiry_dates(
        self, symbol: str, exchange_segment: str = "NSEFO", series: str = "OPTIDX"
    ) -> List[str]:
        cache_key = f"{exchange_segment}:{symbol}"
        if cache_key not in self._expiry_cache:
            try:
                result = await self.market_client.get_expiry_dates(exchange_segment, series, symbol)
                expiries = result.get("result", [])
                self._expiry_cache[cache_key] = sorted(expiries)
            except Exception as e:
                logger.error("Failed to get expiry dates", symbol=symbol, error=str(e))
                return []
        return self._expiry_cache[cache_key]

    async def get_nearest_expiry(self, symbol: str) -> Optional[str]:
        expiries = await self.get_expiry_dates(symbol)
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        for exp in expiries:
            try:
                exp_date = datetime.strptime(exp, "%b %d %Y")
                if exp_date >= today:
                    return exp
            except (ValueError, AttributeError):
                continue
        return expiries[0] if expiries else None

    async def get_option_instrument(
        self, symbol: str, expiry_date: str, option_type: str, strike_price: float,
        exchange_segment: str = "NSEFO", series: str = "OPTIDX"
    ) -> Optional[Dict]:
        cache_key = f"{symbol}:{expiry_date}:{option_type}:{strike_price}"
        if cache_key not in self._instrument_cache:
            try:
                result = await self.market_client.get_option_symbol(
                    exchange_segment, series, symbol, expiry_date, option_type, strike_price
                )
                instrument = result.get("result", {})
                self._instrument_cache[cache_key] = instrument
            except Exception as e:
                logger.error("Failed to get option instrument", symbol=symbol, strike=strike_price, error=str(e))
                return None
        return self._instrument_cache[cache_key]

    def get_atm_strike(self, spot_price: float, strike_interval: float = 50.0) -> float:
        """Get nearest ATM strike."""
        return round(spot_price / strike_interval) * strike_interval

    def get_otm_call_strike(self, spot_price: float, otm_points: float, strike_interval: float = 50.0) -> float:
        atm = self.get_atm_strike(spot_price, strike_interval)
        return atm + otm_points

    def get_otm_put_strike(self, spot_price: float, otm_points: float, strike_interval: float = 50.0) -> float:
        atm = self.get_atm_strike(spot_price, strike_interval)
        return atm - otm_points

    def update_ltp(self, exchange_instrument_id: int, ltp: float):
        self._ltp_cache[exchange_instrument_id] = ltp

    def get_ltp(self, exchange_instrument_id: int) -> Optional[float]:
        return self._ltp_cache.get(exchange_instrument_id)
