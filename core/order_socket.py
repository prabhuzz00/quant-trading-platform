import asyncio
import json
from typing import Any, Optional
import socketio
import structlog
from core.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)

ORDER_SOCKET_EVENTS = ["order", "trade", "position", "tradeConversion", "logout", "error", "joined"]


class OrderSocket:
    def __init__(self, url: str, token: str, user_id: str, event_bus: EventBus):
        self.url = url
        self.token = token
        self.user_id = user_id
        self.event_bus = event_bus
        self._sio: Optional[socketio.AsyncClient] = None
        self._connected = False
        self._running = False

    def _build_connection_url(self) -> str:
        return f"{self.url}/?token={self.token}&userID={self.user_id}&apiType=INTERACTIVE"

    async def connect(self):
        self._sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=10,
            logger=False,
            engineio_logger=False,
        )
        self._register_handlers()
        conn_url = self._build_connection_url()
        await self._sio.connect(conn_url, socketio_path="/interactive/socket.io", transports=["websocket"])
        self._running = True
        logger.info("OrderSocket connected")

    def _register_handlers(self):
        @self._sio.event
        async def connect():
            self._connected = True
            logger.info("OrderSocket: connected")

        @self._sio.event
        async def disconnect():
            self._connected = False
            logger.warning("OrderSocket: disconnected")

        for evt in ORDER_SOCKET_EVENTS:
            async def handler(data, _evt=evt):
                await self._handle_event(_evt, data)
            self._sio.on(evt, handler)

    async def _handle_event(self, event_name: str, data: Any):
        try:
            if isinstance(data, str):
                parsed = json.loads(data)
            else:
                parsed = data
            if event_name == "order":
                etype = EventType.ORDER_UPDATE
            elif event_name == "trade":
                etype = EventType.TRADE_UPDATE
            elif event_name == "position":
                etype = EventType.POSITION_UPDATE
            else:
                etype = EventType.SYSTEM
            await self.event_bus.publish(
                Event(event_type=etype, data={"event": event_name, "payload": parsed}, source="order_socket")
            )
        except Exception as e:
            logger.error("OrderSocket event handling error", event=event_name, error=str(e))

    async def disconnect(self):
        self._running = False
        if self._sio and self._connected:
            await self._sio.disconnect()

    def is_connected(self) -> bool:
        """Return True when the WebSocket transport is alive."""
        return self._connected
