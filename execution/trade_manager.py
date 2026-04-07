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


def _unwrap_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the inner XTS payload from an event-bus wrapper.

    The OrderSocket publishes events with the shape:
        {"event": "order", "payload": { ...XTS fields... }}
    However, direct callers (e.g. tests) may pass the XTS dict directly.
    This helper transparently handles both cases.
    """
    if "payload" in data and isinstance(data["payload"], dict):
        return data["payload"]
    return data


class TradeManager:
    """
    Tracks open and closed trades.
    Subscribes to ORDER_UPDATE and TRADE_UPDATE events from the event bus.
    Maintains a live P&L view for all active trades.
    """

    def __init__(self, event_bus: EventBus, db_session_factory=None):
        self.event_bus = event_bus
        self._db_session_factory = db_session_factory
        self._trades: Dict[str, Dict] = {}
        self._order_update_queue: asyncio.Queue = None
        self._trade_update_queue: asyncio.Queue = None
        self._running = False

    async def start(self):
        await self._load_trades_from_db()
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
        payload = _unwrap_payload(data)
        order_id = str(payload.get("AppOrderID") or payload.get("order_id", ""))
        status = payload.get("OrderStatus") or payload.get("status", "")
        symbol = payload.get("TradingSymbol") or payload.get("symbol", "")

        # Map XTS OrderSide to action
        side_raw = payload.get("OrderSide", "")
        if side_raw == "BUY" or side_raw == "Buy":
            action = "BUY"
        elif side_raw == "SELL" or side_raw == "Sell":
            action = "SELL"
        else:
            action = str(side_raw).upper() if side_raw else "BUY"

        if order_id not in self._trades:
            self._trades[order_id] = {
                "order_id": order_id,
                "symbol": symbol,
                "action": action,
                "quantity": int(payload.get("OrderQuantity", 0) or 0),
                "exchange_segment": payload.get("ExchangeSegment", ""),
                "exchange_instrument_id": int(payload.get("ExchangeInstrumentID", 0) or 0),
                "order_mode": payload.get("ProductType", "REGULAR") or "REGULAR",
                "limit_price": float(payload.get("OrderPrice", 0) or 0),
                "strategy_name": payload.get("strategy_name", "Manual"),
                "signal_id": payload.get("signal_id", None),
                "stoploss_points": float(payload.get("stoploss_points", 0) or 0),
                "target_points": float(payload.get("target_points", 0) or 0),
                "status": TRADE_PENDING,
                "filled_qty": 0,
                "avg_price": 0.0,
                "pnl": 0.0,
                "reason": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

        trade = self._trades[order_id]
        trade["updated_at"] = datetime.now(timezone.utc)

        if status in ("Filled", "FILLED"):
            trade["status"] = TRADE_OPEN
            trade["filled_qty"] = int(payload.get("OrderQuantity", trade["filled_qty"]) or trade["filled_qty"])
            trade["avg_price"] = float(payload.get("OrderAverageTradedPrice", trade["avg_price"]) or trade["avg_price"])
            # Persist to database
            await self._persist_trade(trade)
        elif status in ("Cancelled", "REJECTED", "Rejected"):
            trade["status"] = TRADE_CLOSED
            trade["reason"] = payload.get("CancelRejectReason", "") or payload.get("OtherReason", "")
            await self._persist_trade(trade)

        logger.debug("Trade updated from order event", order_id=order_id, status=status)

    async def _handle_trade_update(self, data: Dict[str, Any]):
        payload = _unwrap_payload(data)
        order_id = str(payload.get("AppOrderID") or payload.get("order_id", ""))
        if order_id in self._trades:
            trade = self._trades[order_id]
            trade["updated_at"] = datetime.now(timezone.utc)
            # Update P&L if provided
            if "pnl" in payload:
                trade["pnl"] = payload["pnl"]
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

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _load_trades_from_db(self):
        """Load persisted trades from the database on startup."""
        if self._db_session_factory is None:
            return
        try:
            from database.models import Trade as TradeModel
            from sqlalchemy import select

            async with self._db_session_factory() as session:
                result = await session.execute(select(TradeModel))
                rows = result.scalars().all()
                for row in rows:
                    self._trades[row.order_id] = {
                        "order_id": row.order_id,
                        "signal_id": row.signal_id,
                        "strategy_name": row.strategy_name or "Manual",
                        "symbol": row.symbol,
                        "exchange_segment": row.exchange_segment or "",
                        "exchange_instrument_id": row.exchange_instrument_id or 0,
                        "action": row.action or "BUY",
                        "order_mode": row.order_mode or "REGULAR",
                        "quantity": row.quantity or 0,
                        "limit_price": row.limit_price or 0.0,
                        "filled_qty": row.filled_qty or 0,
                        "avg_price": row.avg_price or 0.0,
                        "stoploss_points": row.stoploss_points or 0.0,
                        "target_points": row.target_points or 0.0,
                        "pnl": row.pnl or 0.0,
                        "status": row.status or TRADE_PENDING,
                        "reason": row.reason,
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                    }
                logger.info("Loaded trades from database", count=len(rows))
        except Exception as e:
            logger.error("Failed to load trades from database", error=str(e))

    async def _persist_trade(self, trade: Dict[str, Any]):
        """Upsert a trade record to the database."""
        if self._db_session_factory is None:
            return
        try:
            from database.models import Trade as TradeModel
            from sqlalchemy import select

            async with self._db_session_factory() as session:
                result = await session.execute(
                    select(TradeModel).where(TradeModel.order_id == trade["order_id"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.symbol = trade.get("symbol", existing.symbol)
                    existing.filled_qty = trade.get("filled_qty", existing.filled_qty)
                    existing.avg_price = trade.get("avg_price", existing.avg_price)
                    existing.pnl = trade.get("pnl", existing.pnl)
                    existing.status = trade.get("status", existing.status)
                    existing.reason = trade.get("reason", existing.reason)
                else:
                    new_trade = TradeModel(
                        order_id=trade["order_id"],
                        signal_id=trade.get("signal_id"),
                        strategy_name=trade.get("strategy_name", "Manual"),
                        symbol=trade.get("symbol", ""),
                        exchange_segment=trade.get("exchange_segment", ""),
                        exchange_instrument_id=trade.get("exchange_instrument_id", 0),
                        action=trade.get("action", "BUY"),
                        order_mode=trade.get("order_mode", "REGULAR"),
                        quantity=trade.get("quantity", 0),
                        limit_price=trade.get("limit_price", 0.0),
                        filled_qty=trade.get("filled_qty", 0),
                        avg_price=trade.get("avg_price", 0.0),
                        stoploss_points=trade.get("stoploss_points", 0.0),
                        target_points=trade.get("target_points", 0.0),
                        pnl=trade.get("pnl", 0.0),
                        status=trade.get("status", TRADE_PENDING),
                        reason=trade.get("reason"),
                    )
                    session.add(new_trade)
                await session.commit()
        except Exception as e:
            logger.error("Failed to persist trade to database", error=str(e), order_id=trade.get("order_id"))
