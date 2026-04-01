from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import structlog
from engine.signal import Signal

if TYPE_CHECKING:
    from core.candle_store import CandleStore

logger = structlog.get_logger(__name__)


class BaseStrategy(ABC):
    def __init__(self, name: str, enabled: bool = False):
        self.name = name
        self.enabled = enabled
        # Set to True for strategies that require historical candles before
        # generating signals (e.g. SMC Confluence, Volume Breakout).
        self.warmup_required: bool = False
        # Minimum number of historical candles needed for indicator calculation.
        self.lookback_period: int = 50
        # Injected by the application bootstrap when warmup_required is True.
        self.candle_store: Optional["CandleStore"] = None

    @abstractmethod
    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        """Process a tick event and return any signals generated."""
        ...

    @abstractmethod
    async def on_order_update(self, data: Dict[str, Any]) -> None:
        """Handle an order update event."""
        ...

    async def on_bar(self, data: Dict[str, Any]) -> List[Signal]:
        """Process a bar/candle event and return any signals generated."""
        return []

    def get_instruments_to_subscribe(self) -> List[Dict[str, Any]]:
        """Return list of instruments this strategy wants to subscribe to."""
        return []

    def get_warmup_instruments(self) -> List[Dict[str, Any]]:
        """
        Return the list of instrument specs needed for historical warm-up.

        Each entry is a dict with keys:
          - ``exchange_segment``       (str)   e.g. ``"NSECM"``
          - ``exchange_instrument_id`` (int)
          - ``timeframe``              (int)   candle size in minutes, default 5
          - ``n_candles``              (int)   bars to fetch, defaults to
                                               ``self.lookback_period``

        Strategies that set ``warmup_required = True`` **must** override this
        method to declare which (instrument, timeframe) pairs they need.
        """
        return []
