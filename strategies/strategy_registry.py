from typing import Dict, List, Type
import structlog
from strategies.base_strategy import BaseStrategy

logger = structlog.get_logger(__name__)


class StrategyRegistry:
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy):
        self._strategies[strategy.name] = strategy
        logger.info("Strategy registered", name=strategy.name)

    def unregister(self, name: str):
        self._strategies.pop(name, None)
        logger.info("Strategy unregistered", name=name)

    def get_strategy(self, name: str) -> BaseStrategy:
        return self._strategies[name]

    def get_enabled_strategies(self) -> List[BaseStrategy]:
        return [s for s in self._strategies.values() if s.enabled]

    def get_all_strategies(self) -> List[BaseStrategy]:
        return list(self._strategies.values())
