"""Kill switch: halts all trading activity immediately."""
import asyncio
from datetime import datetime, timezone
from typing import Optional
import structlog

from core.event_bus import EventBus, EventType, Event

logger = structlog.get_logger(__name__)


class KillSwitch:
    """
    Global kill switch for the trading platform.
    When activated, it publishes a KILL_SWITCH event and prevents new orders.
    Can be triggered manually or automatically on breach of risk limits.
    """

    def __init__(self, event_bus: EventBus, order_manager=None):
        self.event_bus = event_bus
        self.order_manager = order_manager
        self._activated: bool = False
        self._activated_at: Optional[datetime] = None
        self._reason: str = ""

    @property
    def is_activated(self) -> bool:
        return self._activated

    async def activate(self, reason: str = "Manual kill switch", squareoff: bool = True) -> None:
        if self._activated:
            logger.warning("Kill switch already activated")
            return

        self._activated = True
        self._activated_at = datetime.now(timezone.utc)
        self._reason = reason

        logger.critical("KILL SWITCH ACTIVATED", reason=reason)

        await self.event_bus.publish(Event(
            event_type=EventType.KILL_SWITCH,
            data={"reason": reason, "activated_at": self._activated_at.isoformat()},
            source="KillSwitch",
        ))

        if squareoff and self.order_manager:
            try:
                count = await self.order_manager.squareoff_all()
                logger.info("Kill switch squared off all positions", count=count)
            except Exception as e:
                logger.error("Kill switch failed to square off positions", error=str(e))

    def deactivate(self) -> None:
        """Manually deactivate kill switch (requires manual intervention)."""
        if not self._activated:
            return
        self._activated = False
        self._reason = ""
        self._activated_at = None
        logger.warning("Kill switch deactivated manually")

    def get_status(self) -> dict:
        return {
            "activated": self._activated,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "reason": self._reason,
        }
