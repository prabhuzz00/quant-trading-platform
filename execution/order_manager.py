"""Order manager: translates approved signals into XTS API calls."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import structlog

from core.event_bus import EventBus, EventType, Event
from engine.signal import Signal, SignalAction, OrderMode

logger = structlog.get_logger(__name__)

ORDER_PENDING = "PENDING"
ORDER_OPEN = "OPEN"
ORDER_FILLED = "FILLED"
ORDER_CANCELLED = "CANCELLED"
ORDER_REJECTED = "REJECTED"


class OrderManager:
    """
    Subscribes to SIGNAL events from the event bus.
    Passes signals through risk_manager before placing orders.
    Translates approved signals into XTS API calls.
    Supports BRACKET, COVER, and REGULAR order modes.
    """

    def __init__(self, event_bus: EventBus, xts_client=None, risk_manager=None):
        self.event_bus = event_bus
        self.xts_client = xts_client
        self.risk_manager = risk_manager
        self._pending_orders: Dict[str, Dict] = {}
        self._signal_queue: asyncio.Queue = None
        self._running = False

    async def start(self):
        self._signal_queue = self.event_bus.subscribe(EventType.SIGNAL)
        self._running = True
        asyncio.create_task(self._process_signals())
        logger.info("OrderManager started")

    async def stop(self):
        self._running = False
        logger.info("OrderManager stopped")

    async def _process_signals(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._signal_queue.get(), timeout=1.0)
                signal: Signal = event.data
                await self._handle_signal(signal)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error processing signal", error=str(e))

    async def _handle_signal(self, signal: Signal):
        if self.risk_manager:
            approved, reason = await self.risk_manager.check_signal(signal, None)
            if not approved:
                logger.warning("Signal rejected by risk manager", reason=reason, signal_id=signal.signal_id)
                await self._emit_audit("SIGNAL_REJECTED", {"signal_id": signal.signal_id, "reason": reason})
                return

        try:
            order_id = await self._place_order(signal)
            if order_id:
                self._pending_orders[order_id] = {
                    "order_unique_id": order_id,
                    "signal": signal,
                    "state": ORDER_PENDING,
                    "created_at": datetime.now(timezone.utc),
                }
                await self._emit_audit("ORDER_PLACED", {
                    "order_unique_id": order_id,
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "action": signal.action,
                    "quantity": signal.quantity,
                    "order_mode": signal.order_mode,
                })
        except Exception as e:
            logger.error("Failed to place order", error=str(e), signal_id=signal.signal_id)
            await self._emit_audit("ORDER_FAILED", {"signal_id": signal.signal_id, "error": str(e)})

    async def _place_order(self, signal: Signal) -> Optional[str]:
        if self.xts_client is None:
            logger.warning("No XTS client configured, simulating order placement")
            return uuid.uuid4().hex[:16]

        order_unique_id = uuid.uuid4().hex[:16]
        product_type = self._get_product_type(signal.order_mode)
        order_type = "LIMIT" if signal.limit_price > 0 else "MARKET"

        if signal.order_mode == OrderMode.BRACKET:
            result = await self.xts_client.place_bracket_order(
                exchange_segment=signal.exchange_segment,
                exchange_instrument_id=signal.exchange_instrument_id,
                order_side=signal.action.value,
                order_quantity=signal.quantity,
                limit_price=signal.limit_price,
                squareoff=signal.target_points,
                stop_loss_price=signal.stoploss_points,
                trailing_stoploss=signal.trailing_sl,
                product_type=product_type,
                order_type=order_type,
                order_unique_identifier=order_unique_id,
            )
        elif signal.order_mode == OrderMode.COVER:
            result = await self.xts_client.place_cover_order(
                exchange_segment=signal.exchange_segment,
                exchange_instrument_id=signal.exchange_instrument_id,
                order_side=signal.action.value,
                order_quantity=signal.quantity,
                limit_price=signal.limit_price,
                stop_price=signal.stoploss_points,
                product_type=product_type,
                order_type=order_type,
                order_unique_identifier=order_unique_id,
            )
        else:
            result = await self.xts_client.place_order(
                exchange_segment=signal.exchange_segment,
                exchange_instrument_id=signal.exchange_instrument_id,
                order_side=signal.action.value,
                order_quantity=signal.quantity,
                limit_price=signal.limit_price,
                product_type=product_type,
                order_type=order_type,
                order_unique_identifier=order_unique_id,
            )

        logger.info("Order placed", order_unique_id=order_unique_id, symbol=signal.symbol)
        return order_unique_id

    def _get_product_type(self, order_mode: OrderMode) -> str:
        mapping = {
            OrderMode.BRACKET: "BO",
            OrderMode.COVER: "CO",
            OrderMode.REGULAR: "NRML",
        }
        return mapping.get(order_mode, "NRML")

    async def squareoff_trade(self, trade_id: str) -> bool:
        """Square off a specific trade by its order_unique_id."""
        order_info = self._pending_orders.get(trade_id)
        if not order_info:
            logger.warning("Trade not found for squareoff", trade_id=trade_id)
            return False

        try:
            if self.xts_client:
                await self.xts_client.squareoff_position(
                    exchange_segment=order_info["signal"].exchange_segment,
                    exchange_instrument_id=order_info["signal"].exchange_instrument_id,
                    product_type=self._get_product_type(order_info["signal"].order_mode),
                    squareoff_qty_value=order_info["signal"].quantity,
                )
            order_info["state"] = ORDER_CANCELLED
            await self._emit_audit("TRADE_SQUAREDOFF", {"trade_id": trade_id})
            logger.info("Trade squared off", trade_id=trade_id)
            return True
        except Exception as e:
            logger.error("Failed to square off trade", trade_id=trade_id, error=str(e))
            return False

    async def squareoff_all(self) -> int:
        """Square off all open orders. Returns count of squared-off trades."""
        open_orders = [
            oid for oid, info in self._pending_orders.items()
            if info["state"] in (ORDER_PENDING, ORDER_OPEN)
        ]
        count = 0
        for order_id in open_orders:
            if await self.squareoff_trade(order_id):
                count += 1
        logger.info("All trades squared off", count=count)
        await self._emit_audit("SQUAREOFF_ALL", {"count": count})
        return count

    async def _emit_audit(self, action: str, details: Dict):
        await self.event_bus.publish(Event(
            event_type=EventType.SYSTEM,
            data={"audit": True, "action": action, "details": details, "actor": "system"},
            source="OrderManager",
        ))

    def get_pending_orders(self) -> Dict[str, Dict]:
        return dict(self._pending_orders)
