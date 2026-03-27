from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    EXIT_ALL = "EXIT_ALL"


class OrderMode(str, Enum):
    BRACKET = "BRACKET"
    COVER = "COVER"
    REGULAR = "REGULAR"


@dataclass
class Signal:
    strategy_name: str
    action: SignalAction
    exchange_segment: str
    exchange_instrument_id: int
    symbol: str
    quantity: int
    order_mode: OrderMode = OrderMode.BRACKET
    limit_price: float = 0.0
    target_points: float = 0.0
    stoploss_points: float = 0.0
    trailing_sl: float = 0.0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    signal_id: str = field(default_factory=lambda: __import__('uuid').uuid4().hex[:12])
