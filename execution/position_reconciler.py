"""Position reconciler: compares local position state with broker positions."""
import asyncio
from typing import Any, Dict, List, Optional
import structlog

from core.event_bus import EventBus, EventType, Event

logger = structlog.get_logger(__name__)


class PositionReconciler:
    """
    Periodically fetches broker positions via xts_client and compares them
    with the local trade_manager state to detect discrepancies.
    Publishes POSITION_UPDATE events for each reconciled position.
    """

    def __init__(
        self,
        event_bus: EventBus,
        xts_client=None,
        trade_manager=None,
        reconcile_interval: int = 60,
    ):
        self.event_bus = event_bus
        self.xts_client = xts_client
        self.trade_manager = trade_manager
        self.reconcile_interval = reconcile_interval
        self._running = False
        self._positions: Dict[str, Dict] = {}

    async def start(self):
        self._running = True
        asyncio.create_task(self._reconcile_loop())
        logger.info("PositionReconciler started", interval=self.reconcile_interval)

    async def stop(self):
        self._running = False
        logger.info("PositionReconciler stopped")

    async def _reconcile_loop(self):
        while self._running:
            try:
                await self._reconcile()
            except Exception as e:
                logger.error("Reconciliation error", error=str(e))
            await asyncio.sleep(self.reconcile_interval)

    async def _reconcile(self):
        broker_positions = await self._fetch_broker_positions()
        if broker_positions is None:
            return

        for pos in broker_positions:
            instrument_id = pos.get("ExchangeInstrumentID") or pos.get("instrument_id", "")
            self._positions[str(instrument_id)] = pos
            await self.event_bus.publish(Event(
                event_type=EventType.POSITION_UPDATE,
                data=pos,
                source="PositionReconciler",
            ))

        if self.trade_manager:
            open_trades = self.trade_manager.get_open_trades()
            broker_ids = {
                str(p.get("ExchangeInstrumentID") or p.get("instrument_id", ""))
                for p in broker_positions
            }
            for trade in open_trades:
                symbol = trade.get("symbol", "")
                if symbol not in broker_ids:
                    logger.warning(
                        "Position mismatch: local trade not found in broker positions",
                        symbol=symbol,
                        order_id=trade.get("order_id"),
                    )

        logger.debug("Position reconciliation complete", count=len(broker_positions))

    async def _fetch_broker_positions(self) -> Optional[List[Dict]]:
        if self.xts_client is None:
            logger.debug("No XTS client; skipping broker position fetch")
            return []
        try:
            result = await self.xts_client.get_positions()
            if isinstance(result, dict):
                return result.get("positionList", [])
            return result or []
        except Exception as e:
            logger.error("Failed to fetch broker positions", error=str(e))
            return None

    def get_positions(self) -> Dict[str, Dict]:
        return dict(self._positions)
