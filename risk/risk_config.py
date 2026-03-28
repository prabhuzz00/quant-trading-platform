from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RiskConfig:
    max_capital: float = 500000.0
    max_margin_utilization: float = 0.80
    max_open_trades: int = 10
    max_daily_loss: float = 25000.0
    max_per_strategy_trades: int = 2
    max_per_strategy_capital: float = 100000.0
    max_quantity_per_order: int = 50
    cooldown_seconds: int = 60
    trading_enabled: bool = True
    allowed_symbols: List[str] = field(default_factory=lambda: ["NIFTY", "BANKNIFTY"])
    allowed_segments: List[str] = field(default_factory=lambda: ["NSEFO"])
