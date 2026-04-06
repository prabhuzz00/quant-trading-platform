import asyncio
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
import socketio
import structlog
from core.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)

SOCKET_EVENTS = {
    "1501-json-full": "touchline",
    "1502-json-full": "market_depth",
    "1505-json-full": "candle",
    "1510-json-full": "open_interest",
    "1512-json-full": "ltp",
    "1501-json-partial": "touchline_partial",
    "1502-json-partial": "market_depth_partial",
    "1505-json-partial": "candle_partial",
    "1510-json-partial": "oi_partial",
    "1512-json-partial": "ltp_partial",
}


class MarketDataSocket:
    # XTS message code for candle (OHLC) subscriptions
    _CANDLE_MESSAGE_CODE = 1505

    def __init__(self, url: str, token: str, user_id: str, event_bus: EventBus,
                 xts_client=None, broadcast_mode: str = "Full"):
        self.url = url
        self.token = token
        self.user_id = user_id
        self.event_bus = event_bus
        self.xts_client = xts_client
        self.broadcast_mode = broadcast_mode
        self._sio: Optional[socketio.AsyncClient] = None
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect = 10
        self._running = False

    def _build_connection_url(self) -> str:
        return (
            f"{self.url}/?token={self.token}&userID={self.user_id}"
            f"&publishFormat=JSON&broadcastMode={self.broadcast_mode}"
        )

    async def connect(self):
        self._sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_attempts=self._max_reconnect,
            logger=False,
            engineio_logger=False,
        )
        self._register_handlers()
        conn_url = self._build_connection_url()
        await self._sio.connect(conn_url, socketio_path="/apimarketdata/socket.io", transports=["websocket"])
        self._running = True
        logger.info("MarketDataSocket connected")

    def _register_handlers(self):
        @self._sio.event
        async def connect():
            self._connected = True
            self._reconnect_attempts = 0
            logger.info("MarketDataSocket: connected")

        @self._sio.event
        async def disconnect():
            self._connected = False
            logger.warning("MarketDataSocket: disconnected")

        @self._sio.event
        async def connect_error(data):
            logger.error("MarketDataSocket: connection error", error=str(data))

        for event_name in SOCKET_EVENTS:
            async def handler(data, _evt=event_name):
                await self._handle_event(_evt, data)
            self._sio.on(event_name, handler)

    # XTS socket events that carry completed candle (bar) data
    _CANDLE_EVENTS = frozenset({"1505-json-full", "1505-json-partial"})

    async def _handle_event(self, event_name: str, data: Any):
        try:
            if isinstance(data, str):
                parsed = json.loads(data)
            else:
                parsed = data
            event_type_name = SOCKET_EVENTS.get(event_name, "unknown")
            payload = {"type": event_type_name, "event": event_name, "payload": parsed}

            # Publish candle (bar) events on EventType.BAR so that the
            # StrategyEngine can update the CandleStore and route to on_bar().
            if event_name in self._CANDLE_EVENTS:
                bar_event = Event(
                    event_type=EventType.BAR,
                    data=payload,
                    source="market_data_socket",
                )
                await self.event_bus.publish(bar_event)
            else:
                tick_event = Event(
                    event_type=EventType.TICK,
                    data=payload,
                    source="market_data_socket",
                )
                await self.event_bus.publish(tick_event)
        except Exception as e:
            logger.error("MarketDataSocket event handling error", event=event_name, error=str(e))

    async def subscribe_candles(self, instruments: List[Dict[str, Any]]) -> None:
        """Subscribe to live candle (1505) events for the given instruments.

        Parameters
        ----------
        instruments:
            List of dicts with ``exchangeSegment`` and ``exchangeInstrumentID``
            keys, e.g. ``[{"exchangeSegment": 1, "exchangeInstrumentID": 26000}]``.
        """
        if not instruments:
            return
        if self.xts_client is None:
            logger.warning("MarketDataSocket: cannot subscribe to candles – no XTS client attached")
            return
        try:
            result = await self.xts_client.subscribe(
                instruments=instruments,
                xts_message_code=self._CANDLE_MESSAGE_CODE,
            )
            logger.info(
                "MarketDataSocket: subscribed to live candles",
                instruments=len(instruments),
                result_type=result.get("type", ""),
            )
        except Exception as exc:
            logger.warning(
                "MarketDataSocket: candle subscription failed",
                error=str(exc),
            )

    async def disconnect(self):
        self._running = False
        if self._sio and self._connected:
            await self._sio.disconnect()

    def is_connected(self) -> bool:
        """Return True when the WebSocket transport is alive."""
        return self._connected
