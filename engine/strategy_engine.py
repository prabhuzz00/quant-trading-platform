import asyncio
from typing import Dict, List
import structlog
from core.event_bus import EventBus, Event, EventType
from engine.signal import Signal
from strategies.base_strategy import BaseStrategy
from strategies.strategy_registry import StrategyRegistry

logger = structlog.get_logger(__name__)


class StrategyEngine:
    def __init__(self, event_bus: EventBus, strategy_registry: StrategyRegistry):
        self.event_bus = event_bus
        self.strategy_registry = strategy_registry
        self._tick_queue: asyncio.Queue = None
        self._order_queue: asyncio.Queue = None
        self._running = False

    async def start(self):
        self._tick_queue = self.event_bus.subscribe(EventType.TICK)
        self._order_queue = self.event_bus.subscribe(EventType.ORDER_UPDATE)
        self._running = True
        logger.info("StrategyEngine started")
        await asyncio.gather(
            self._tick_loop(),
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

    async def _process_order_event(self, event: Event):
        strategies = self.strategy_registry.get_enabled_strategies()
        for strategy in strategies:
            try:
                await strategy.on_order_update(event.data)
            except Exception as e:
                logger.error("Strategy on_order_update error", strategy=strategy.name, error=str(e))
