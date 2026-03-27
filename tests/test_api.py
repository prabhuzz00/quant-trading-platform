"""Tests for FastAPI endpoints using httpx AsyncClient."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Build a minimal test app without full lifespan
from api.routes import trades, risk, strategies
from api.dependencies import (
    get_trade_manager, get_order_manager, get_risk_manager,
    get_strategy_registry, get_kill_switch,
)
from risk.risk_config import RiskConfig
from risk.kill_switch import KillSwitch
from strategies.strategy_registry import StrategyRegistry
from strategies.short_straddle import ShortStraddle
from strategies.short_strangle import ShortStrangle
from strategies.iron_condor import IronCondor
from strategies.bull_call_spread import BullCallSpread
from strategies.bear_put_spread import BearPutSpread
from strategies.long_straddle import LongStraddle
from strategies.butterfly_spread import ButterflySpread
from strategies.calendar_spread import CalendarSpread
from strategies.covered_call import CoveredCall
from strategies.protective_put import ProtectivePut
from core.event_bus import EventBus
from execution.trade_manager import TradeManager


def _build_test_app():
    """Build a minimal FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    event_bus_mock = MagicMock(spec=EventBus)
    event_bus_mock.subscribe.return_value = __import__('asyncio').Queue()

    trade_mgr = TradeManager(event_bus=event_bus_mock)

    risk_cfg = RiskConfig()
    kill_sw = KillSwitch(event_bus=MagicMock())
    kill_sw.event_bus.publish = AsyncMock()

    rm = MagicMock()
    rm.config = risk_cfg
    rm.get_daily_loss.return_value = 0.0
    rm.update_config = MagicMock()

    registry = StrategyRegistry()
    for cls in [
        IronCondor, ShortStraddle, ShortStrangle, BullCallSpread, BearPutSpread,
        LongStraddle, ButterflySpread, CalendarSpread, CoveredCall, ProtectivePut,
    ]:
        registry.register(cls())

    order_mgr = MagicMock()
    order_mgr.squareoff_trade = AsyncMock(return_value=True)
    order_mgr.squareoff_all = AsyncMock(return_value=0)

    app.dependency_overrides[get_trade_manager] = lambda: trade_mgr
    app.dependency_overrides[get_order_manager] = lambda: order_mgr
    app.dependency_overrides[get_risk_manager] = lambda: rm
    app.dependency_overrides[get_strategy_registry] = lambda: registry
    app.dependency_overrides[get_kill_switch] = lambda: kill_sw

    app.include_router(trades.router, prefix="/api")
    app.include_router(risk.router, prefix="/api")
    app.include_router(strategies.router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok", "market_connected": False, "order_connected": False}

    return app


@pytest.fixture
def test_app():
    return _build_test_app()


@pytest.mark.asyncio
async def test_health(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_open_trades(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/trades/open")
    assert resp.status_code == 200
    body = resp.json()
    assert "trades" in body
    assert isinstance(body["trades"], list)


@pytest.mark.asyncio
async def test_get_closed_trades(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/trades/closed")
    assert resp.status_code == 200
    body = resp.json()
    assert "trades" in body
    assert isinstance(body["trades"], list)


@pytest.mark.asyncio
async def test_get_risk_config(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/risk/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "max_open_trades" in body
    assert "trading_enabled" in body


@pytest.mark.asyncio
async def test_list_strategies_returns_10(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/strategies")
    assert resp.status_code == 200
    strategies_list = resp.json()
    assert len(strategies_list) == 10


@pytest.mark.asyncio
async def test_toggle_strategy(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.put(
            "/api/strategies/short_straddle/toggle",
            json={"enabled": False},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "short_straddle"
    assert body["enabled"] is False


@pytest.mark.asyncio
async def test_activate_kill_switch(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            "/api/risk/kill-switch/activate",
            json={"reason": "Test activation"},
        )
    assert resp.status_code == 200
    assert "activated" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_deactivate_kill_switch(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/api/risk/kill-switch/deactivate")
    assert resp.status_code == 200
    assert "deactivated" in resp.json()["message"].lower()
