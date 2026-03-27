"""Trade manager: tracks active trades and handles P&L monitoring."""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

from core.event_bus import EventBus, EventType, Event
from engine.signal import Signal

logger = structlog.get_logger(__name__)

TRADE_OPEN = "OPEN"
TRADE_CLOSED = "CLOSED"
TRADE_PENDING = "PENDING"


class TradeManager:
    """
    Tracks open and closed trades.
    Subscribes to ORDER_UPDATE and TRADE_UPDATE events from the event bus.
    Maintains a live P&L view for all active trades.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._trades: Dict[str, Dict] = {}
        self._order_update_queue: asyncio.Queue = None
        self._trade_update_queue: asyncio.Queue = None
        self._running = False

    async def start(self):
        self._order_update_queue = self.event_bus.subscribe(EventType.ORDER_UPDATE)
        self._trade_update_queue = self.event_bus.subscribe(EventType.TRADE_UPDATE)
        self._running = True
        asyncio.create_task(self._process_order_updates())
        asyncio.create_task(self._process_trade_updates())
        logger.info("TradeManager started")

    async def stop(self):
        self._running = False
        logger.info("TradeManager stopped")

    async def _process_order_updates(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._order_update_queue.get(), timeout=1.0)
                await self._handle_order_update(event.data)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error processing order update", error=str(e))

    async def _process_trade_updates(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._trade_update_queue.get(), timeout=1.0)
                await self._handle_trade_update(event.data)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error processing trade update", error=str(e))

    async def _handle_order_update(self, data: Dict[str, Any]):
        order_id = data.get("AppOrderID") or data.get("order_id", "")
        status = data.get("OrderStatus") or data.get("status", "")
        symbol = data.get("TradingSymbol") or data.get("symbol", "")

        if order_id not in self._trades:
            self._trades[order_id] = {
                "order_id": order_id,
                "symbol": symbol,
                "status": TRADE_PENDING,
                "filled_qty": 0,
                "avg_price": 0.0,
                "pnl": 0.0,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "raw": data,
            }

        trade = self._trades[order_id]
        trade["updated_at"] = datetime.now(timezone.utc)
        trade["raw"] = data

        if status in ("Filled", "FILLED"):
            trade["status"] = TRADE_OPEN
            trade["filled_qty"] = data.get("OrderQuantity", trade["filled_qty"])
            trade["avg_price"] = data.get("OrderAverageTradedPrice", trade["avg_price"])
        elif status in ("Cancelled", "REJECTED", "Rejected"):
            trade["status"] = TRADE_CLOSED

        logger.debug("Trade updated from order event", order_id=order_id, status=status)

    async def _handle_trade_update(self, data: Dict[str, Any]):
        order_id = data.get("AppOrderID") or data.get("order_id", "")
        if order_id in self._trades:
            trade = self._trades[order_id]
            trade["updated_at"] = datetime.now(timezone.utc)
            # Update P&L if provided
            if "pnl" in data:
                trade["pnl"] = data["pnl"]
            logger.debug("Trade updated from trade event", order_id=order_id)

    def register_trade(self, order_id: str, signal: Signal):
        """Register a new trade from a placed order."""
        self._trades[order_id] = {
            "order_id": order_id,
            "signal_id": signal.signal_id,
            "strategy_name": signal.strategy_name,
            "symbol": signal.symbol,
            "action": signal.action,
            "quantity": signal.quantity,
            "limit_price": signal.limit_price,
            "status": TRADE_PENDING,
            "filled_qty": 0,
            "avg_price": 0.0,
            "pnl": 0.0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    def get_open_trades(self) -> List[Dict]:
        return [t for t in self._trades.values() if t["status"] == TRADE_OPEN]

    def get_all_trades(self) -> List[Dict]:
        return list(self._trades.values())

    def get_trade(self, order_id: str) -> Optional[Dict]:
        return self._trades.get(order_id)

    def get_total_pnl(self) -> float:
        return sum(t.get("pnl", 0.0) for t in self._trades.values())

    def get_open_trade_count(self) -> int:
        return sum(1 for t in self._trades.values() if t["status"] == TRADE_OPEN)
