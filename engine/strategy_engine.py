import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import structlog
from core.candle_store import Candle, CandleStore
from core.event_bus import EventBus, Event, EventType
from engine.signal import Signal
from strategies.base_strategy import BaseStrategy
from strategies.strategy_registry import StrategyRegistry

logger = structlog.get_logger(__name__)


class StrategyEngine:
    def __init__(
        self,
        event_bus: EventBus,
        strategy_registry: StrategyRegistry,
        candle_store: Optional[CandleStore] = None,
    ):
        self.event_bus = event_bus
        self.strategy_registry = strategy_registry
        self.candle_store = candle_store
        self._tick_queue: asyncio.Queue = None
        self._bar_queue: asyncio.Queue = None
        self._order_queue: asyncio.Queue = None
        self._running = False

    async def start(self):
        self._tick_queue = self.event_bus.subscribe(EventType.TICK)
        self._bar_queue = self.event_bus.subscribe(EventType.BAR)
        self._order_queue = self.event_bus.subscribe(EventType.ORDER_UPDATE)
        self._running = True
        logger.info("StrategyEngine started")
        await asyncio.gather(
            self._tick_loop(),
            self._bar_loop(),
            self._order_loop(),
        )

    async def stop(self):
        self._running = False
        logger.info("StrategyEngine stopped")

    async def _tick_loop(self):
        while self._running:
            try:
                event: Event = await asyncio.wait_for(self._tick_queue.get(), timeout=1.0)
                await self._process_tick(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("StrategyEngine tick loop error", error=str(e))

    async def _bar_loop(self):
        while self._running:
            try:
                event: Event = await asyncio.wait_for(self._bar_queue.get(), timeout=1.0)
                await self._process_bar(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("StrategyEngine bar loop error", error=str(e))

    async def _order_loop(self):
        while self._running:
            try:
                event: Event = await asyncio.wait_for(self._order_queue.get(), timeout=1.0)
                await self._process_order_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("StrategyEngine order loop error", error=str(e))

    async def _process_tick(self, event: Event):
        strategies = self.strategy_registry.get_enabled_strategies()
        signals: List[Signal] = []
        for strategy in strategies:
            try:
                new_signals = await strategy.on_tick(event.data)
                signals.extend(new_signals)
            except Exception as e:
                logger.error("Strategy on_tick error", strategy=strategy.name, error=str(e))

        for signal in signals:
            await self.event_bus.publish(Event(event_type=EventType.SIGNAL, data=signal, source="strategy_engine"))

    async def _process_bar(self, event: Event):
        """Update CandleStore from incoming bar events, then call on_bar()."""
        bar_data: dict = event.data
        payload = bar_data.get("payload", {})

        # ------------------------------------------------------------------
        # Ingest the bar into the CandleStore so strategies have up-to-date
        # history without needing to call the API again.
        # ------------------------------------------------------------------
        if self.candle_store is not None:
            try:
                self._ingest_bar(payload)
            except Exception as exc:
                logger.debug("CandleStore ingest error", error=str(exc))

        # ------------------------------------------------------------------
        # Dispatch to strategies
        # ------------------------------------------------------------------
        strategies = self.strategy_registry.get_enabled_strategies()
        signals: List[Signal] = []
        for strategy in strategies:
            try:
                new_signals = await strategy.on_bar(bar_data)
                signals.extend(new_signals)
            except Exception as e:
                logger.error("Strategy on_bar error", strategy=strategy.name, error=str(e))

        for signal in signals:
            await self.event_bus.publish(Event(event_type=EventType.SIGNAL, data=signal, source="strategy_engine"))

    def _ingest_bar(self, payload: dict) -> None:
        """
        Parse an XTS candle payload and insert a :class:`Candle` into the
        store.  The payload structure expected from the live socket::

            {
                "ExchangeInstrumentID": 26000,
                "ExchangeSegment": 1,
                "Open": 19000.0,
                "High": 19050.0,
                "Low": 18980.0,
                "Close": 19020.0,
                "Volume": 100000,
                "Time": 1609459200   # Unix timestamp
            }
        """
        if self.candle_store is None:
            return

        instrument_id: Optional[int] = (
            payload.get("ExchangeInstrumentID")
            or payload.get("exchangeInstrumentID")
        )
        if not instrument_id:
            return

        raw_ts = payload.get("Time") or payload.get("time") or payload.get("timestamp")
        if isinstance(raw_ts, (int, float)):
            ts = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
        elif raw_ts:
            ts = datetime.fromisoformat(str(raw_ts))
        else:
            ts = datetime.now(timezone.utc)

        # Default to 1-minute timeframe when not specified.  XTS live candle
        # subscriptions include ``CompressionValue`` in the payload; if it is
        # absent we fall back to 1 min and emit a debug log so mismatches are
        # visible during development.
        raw_tf = payload.get("CompressionValue", payload.get("compressionValue"))
        if raw_tf is None:
            logger.debug("CandleStore ingest: CompressionValue missing, defaulting to 1 min", payload=payload)
            raw_tf = 1
        timeframe: int = int(raw_tf)

        candle = Candle(
            timestamp=ts,
            open=float(payload.get("Open", payload.get("open", 0))),
            high=float(payload.get("High", payload.get("high", 0))),
            low=float(payload.get("Low", payload.get("low", 0))),
            close=float(payload.get("Close", payload.get("close", 0))),
            volume=float(payload.get("Volume", payload.get("volume", 0))),
        )
        self.candle_store.add_candle(int(instrument_id), timeframe, candle)

    async def _process_order_event(self, event: Event):
        strategies = self.strategy_registry.get_enabled_strategies()
        for strategy in strategies:
            try:
                await strategy.on_order_update(event.data)
            except Exception as e:
                logger.error("Strategy on_order_update error", strategy=strategy.name, error=str(e))
