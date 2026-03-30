import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime, timezone
import structlog
from core.xts_client import XTSMarketDataClient

logger = structlog.get_logger(__name__)

_MASTER_CACHE_TTL = 3600  # 1 hour


class InstrumentManager:
    """Manages option chain, strike selection, expiry dates."""

    def __init__(self, market_client: XTSMarketDataClient):
        self.market_client = market_client
        self._instrument_cache: Dict[str, Dict] = {}
        self._expiry_cache: Dict[str, List[str]] = {}
        self._ltp_cache: Dict[int, float] = {}
        self._master_cache: Dict[str, List[Dict]] = {}
        self._master_loaded_at: Dict[str, float] = {}

    async def get_expiry_dates(
        self, symbol: str, exchange_segment: str = "NSEFO", series: str = "OPTIDX"
    ) -> List[str]:
        """Return sorted unique expiry dates for *symbol* derived from the master file.

        The XTS ``expiryDate`` endpoint is unreliable (returns 400 for many
        broker configurations).  Instead we download the full instrument master
        once (cached for 1 hour) and extract the distinct expiry dates that
        match *symbol* and *series*.
        """
        cache_key = f"{exchange_segment}:{symbol}:{series}"
        if cache_key not in self._expiry_cache:
            try:
                await self.load_master(exchange_segment)
                seen: set = set()
                for inst in self._master_cache.get(exchange_segment, []):
                    if inst.get("name") != symbol:
                        continue
                    if inst.get("series") != series:
                        continue
                    raw_exp = inst.get("contract_expiration", "").strip()
                    if not raw_exp:
                        continue
                    # Normalise to YYYY-MM-DD to strip any time component and unify formats.
                    normalized = self._normalize_expiry(raw_exp)
                    if normalized:
                        seen.add(normalized)
                # Sort chronologically using the normalised YYYY-MM-DD form
                expiries = sorted(seen, key=lambda e: self._normalize_expiry(e))
                self._expiry_cache[cache_key] = expiries
            except Exception as e:
                logger.error("Failed to get expiry dates", symbol=symbol, error=str(e))
                return []
        return self._expiry_cache[cache_key]

    async def get_nearest_expiry(self, symbol: str) -> Optional[str]:
        expiries = await self.get_expiry_dates(symbol)
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        for exp in expiries:
            norm = self._normalize_expiry(exp)
            try:
                exp_date = datetime.strptime(norm, "%Y-%m-%d")
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

    # ------------------------------------------------------------------
    # Master data: bulk instrument download & option chain
    # ------------------------------------------------------------------

    async def load_master(self, exchange_segment: str = "NSEFO") -> None:
        """Download and cache all instruments for an exchange segment."""
        now = time.monotonic()
        loaded_at = self._master_loaded_at.get(exchange_segment, 0.0)
        if exchange_segment in self._master_cache and (now - loaded_at) < _MASTER_CACHE_TTL:
            return
        result = await self.market_client.get_master([exchange_segment])
        raw = result.get("result", "")
        if not isinstance(raw, str):
            logger.warning("Unexpected master data type", exchange_segment=exchange_segment, type=type(raw).__name__)
            raw = ""
        instruments = self._parse_master(raw)
        self._master_cache[exchange_segment] = instruments
        self._master_loaded_at[exchange_segment] = now
        logger.info("Master data loaded", exchange_segment=exchange_segment, count=len(instruments))

    @staticmethod
    def _parse_master(raw: str) -> List[Dict]:
        """Parse pipe-delimited XTS master data into a list of instrument dicts.

        XTS master columns for NSEFO options (OPTIDX/OPTSTK):
        0  ExchangeSegment  1  ExchangeInstrumentID  2  InstrumentType
        3  Name  4  Description  5  Series  6  NameWithSeries  7  InstrumentID
        8  PriceBand.High  9  PriceBand.Low  10  FreezeQty  11  TickSize
        12  LotSize  13  Multiplier  14  DisplayName  15  ISIN
        16  PriceNumerator  17  PriceDenominator  18  DetailedDescription
        19  ContractExpiration  20  StrikePrice  21  OptionType (CE/PE)
        """
        instruments: List[Dict] = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 19:
                continue
            try:
                inst: Dict = {
                    "exchange_segment": parts[0],
                    "exchange_instrument_id": int(parts[1]),
                    "instrument_type": parts[2],
                    "name": parts[3],
                    "series": parts[5],
                    "display_name": parts[14] if len(parts) > 14 else "",
                    "lot_size": int(parts[12]) if parts[12].isdigit() else 1,
                    "tick_size": float(parts[11]) if parts[11] else 0.05,
                }
                if len(parts) >= 22 and parts[5] in ("OPTIDX", "OPTSTK"):
                    inst["contract_expiration"] = parts[19].strip()
                    try:
                        inst["strike_price"] = float(parts[20])
                    except (ValueError, IndexError):
                        inst["strike_price"] = 0.0
                    inst["option_type"] = parts[21].strip()
                instruments.append(inst)
            except (ValueError, IndexError) as exc:
                logger.debug("Skipping unparseable master row", error=str(exc))
        return instruments

    @staticmethod
    def _normalize_expiry(expiry_str: str) -> str:
        """Normalise an expiry string to YYYY-MM-DD for comparison.

        Handles XTS master data formats that may include a time component,
        e.g. "Apr 24 2025 12:00:00 AM", as well as plain date strings.
        """
        if not expiry_str:
            return ""
        s = expiry_str.strip()
        for fmt in (
            "%b %d %Y %I:%M:%S %p",  # "Apr 24 2025 12:00:00 AM" (XTS master with time)
            "%b %d %Y",               # "Jan 30 2025"
            "%b  %d %Y",              # "Jan  30 2025" (double space)
            "%d%b%Y",                 # "30Jan2025"
            "%Y-%m-%d",               # "2025-01-30"
            "%d-%b-%Y",               # "30-Jan-2025"
            "%d/%m/%Y",               # "30/01/2025"
        ):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return s

    async def get_option_chain_instruments(
        self, symbol: str, expiry_date: str, exchange_segment: str = "NSEFO"
    ) -> List[Dict]:
        """Return all CE/PE instruments for *symbol* and *expiry_date* from master data."""
        await self.load_master(exchange_segment)
        expiry_norm = self._normalize_expiry(expiry_date)
        result: List[Dict] = []
        for inst in self._master_cache.get(exchange_segment, []):
            if inst.get("name") != symbol:
                continue
            if inst.get("series") not in ("OPTIDX", "OPTSTK"):
                continue
            if "option_type" not in inst:
                continue
            if self._normalize_expiry(inst.get("contract_expiration", "")) == expiry_norm:
                result.append(inst)
        return result

    async def invalidate_master_cache(self, exchange_segment: str = "NSEFO") -> None:
        """Force a fresh master download on the next call."""
        self._master_loaded_at.pop(exchange_segment, None)
        self._master_cache.pop(exchange_segment, None)
        # Expiry cache is derived from master data; clear stale entries too.
        stale_keys = [k for k in self._expiry_cache if k.startswith(f"{exchange_segment}:")]
        for k in stale_keys:
            self._expiry_cache.pop(k, None)
