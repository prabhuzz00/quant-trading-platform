import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class EventType(str, Enum):
    TICK = "TICK"
    BAR = "BAR"
    ORDER_UPDATE = "ORDER_UPDATE"
    TRADE_UPDATE = "TRADE_UPDATE"
    POSITION_UPDATE = "POSITION_UPDATE"
    SIGNAL = "SIGNAL"
    KILL_SWITCH = "KILL_SWITCH"
    SYSTEM = "SYSTEM"


@dataclass
class Event:
    event_type: EventType
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""


class EventBus:
    def __init__(self, maxsize: int = 10000):
        self._subscribers: Dict[EventType, List[asyncio.Queue]] = {}
        self._running = False
        self._maxsize = maxsize

    async def start(self):
        self._running = True
        logger.info("EventBus started")

    async def stop(self):
        self._running = False
        logger.info("EventBus stopped")

    def subscribe(self, event_type: EventType) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=self._maxsize)
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(q)
        return q

    async def publish(self, event: Event):
        subscribers = self._subscribers.get(event.event_type, [])
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("EventBus queue full, dropping event", event_type=event.event_type)


event_bus = EventBus()
