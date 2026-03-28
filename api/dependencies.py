"""FastAPI dependency injection providers."""
from typing import AsyncGenerator, Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_session

# Module-level singleton store populated during application lifespan startup.
app_state: Dict[str, Any] = {}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session."""
    async with get_session() as session:
        yield session


def get_trade_manager():
    """Return the initialized TradeManager singleton."""
    return app_state["trade_manager"]


def get_order_manager():
    """Return the initialized OrderManager singleton."""
    return app_state["order_manager"]


def get_risk_manager():
    """Return the initialized RiskManager singleton."""
    return app_state["risk_manager"]


def get_strategy_registry():
    """Return the initialized StrategyRegistry singleton."""
    return app_state["strategy_registry"]


def get_xts_interactive():
    """Return the initialized XTSInteractiveClient singleton."""
    return app_state["xts_interactive"]


def get_xts_market_data():
    """Return the initialized XTSMarketDataClient singleton."""
    return app_state["xts_market_data"]


def get_kill_switch():
    """Return the initialized KillSwitch singleton."""
    return app_state["kill_switch"]


def get_market_data_socket():
    """Return the initialized MarketDataSocket singleton."""
    return app_state.get("market_data_socket")


def get_order_socket():
    """Return the initialized OrderSocket singleton."""
    return app_state.get("order_socket")


def get_instrument_manager():
    """Return the initialized InstrumentManager singleton."""
    return app_state["instrument_manager"]
