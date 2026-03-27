from abc import ABC, abstractmethod
from typing import Any, Dict, List
import structlog
from engine.signal import Signal

logger = structlog.get_logger(__name__)


class BaseStrategy(ABC):
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    @abstractmethod
    async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
        """Process a tick event and return any signals generated."""
        ...

    @abstractmethod
    async def on_order_update(self, data: Dict[str, Any]) -> None:
        """Handle an order update event."""
        ...
