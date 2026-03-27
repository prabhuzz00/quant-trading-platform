"""Risk manager: validates signals and enforces risk limits."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import structlog

from engine.signal import Signal
from risk.risk_config import RiskConfig

logger = structlog.get_logger(__name__)


class RiskManager:
    """
    Enforces pre-trade risk checks before signals are sent to OrderManager.
    Checks include: daily loss limit, open trade count, quantity, symbol/segment
    allowlists, per-strategy limits, and kill switch status.
    """

    def __init__(self, config: Optional[RiskConfig] = None, kill_switch=None, trade_manager=None):
        self.config = config or RiskConfig()
        self.kill_switch = kill_switch
        self.trade_manager = trade_manager
        self._daily_loss: float = 0.0
        self._daily_loss_date: Optional[str] = None

    def _reset_daily_loss_if_new_day(self):
        today = datetime.now(timezone.utc).date().isoformat()
        if self._daily_loss_date != today:
            self._daily_loss = 0.0
            self._daily_loss_date = today

    async def check_signal(self, signal: Signal, context: Any) -> Tuple[bool, str]:
        """
        Validate a signal against risk rules.
        Returns (approved: bool, reason: str).
        """
        self._reset_daily_loss_if_new_day()

        if self.kill_switch and self.kill_switch.is_activated:
            return False, "Kill switch is active"

        if not self.config.trading_enabled:
            return False, "Trading is disabled in risk config"

        if signal.exchange_segment not in self.config.allowed_segments:
            return False, f"Segment {signal.exchange_segment} not in allowed segments"

        base_symbol = signal.symbol.split("_")[0]
        if base_symbol not in self.config.allowed_symbols:
            return False, f"Symbol {base_symbol} not in allowed symbols"

        if signal.quantity > self.config.max_quantity_per_order:
            return False, (
                f"Quantity {signal.quantity} exceeds max {self.config.max_quantity_per_order}"
            )

        if self._daily_loss >= self.config.max_daily_loss:
            return False, (
                f"Daily loss limit reached: {self._daily_loss} >= {self.config.max_daily_loss}"
            )

        if self.trade_manager:
            open_count = self.trade_manager.get_open_trade_count()
            if open_count >= self.config.max_open_trades:
                return False, (
                    f"Max open trades reached: {open_count} >= {self.config.max_open_trades}"
                )

            strategy_trades = sum(
                1 for t in self.trade_manager.get_open_trades()
                if t.get("strategy_name") == signal.strategy_name
            )
            if strategy_trades >= self.config.max_per_strategy_trades:
                return False, (
                    f"Strategy {signal.strategy_name} has reached max trades "
                    f"({strategy_trades} >= {self.config.max_per_strategy_trades})"
                )

        return True, "approved"

    def record_loss(self, amount: float):
        """Record a realized loss for daily tracking."""
        self._reset_daily_loss_if_new_day()
        if amount > 0:
            self._daily_loss += amount
            logger.info("Daily loss updated", daily_loss=self._daily_loss, added=amount)

    def get_daily_loss(self) -> float:
        self._reset_daily_loss_if_new_day()
        return self._daily_loss

    def update_config(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info("Risk config updated", key=key, value=value)
