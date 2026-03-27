"""Tests for RiskManager pre-trade checks."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from engine.signal import Signal, SignalAction, OrderMode
from risk.risk_config import RiskConfig
from risk.risk_manager import RiskManager
from risk.kill_switch import KillSwitch
from core.event_bus import EventBus


def _make_signal(**kwargs) -> Signal:
    defaults = dict(
        strategy_name="short_straddle",
        action=SignalAction.SELL,
        exchange_segment="NSEFO",
        exchange_instrument_id=123,
        symbol="NIFTY_CE",
        quantity=1,
    )
    defaults.update(kwargs)
    return Signal(**defaults)


def _make_risk_manager(config=None, kill_switch=None, trade_manager=None):
    cfg = config or RiskConfig(
        trading_enabled=True,
        max_open_trades=10,
        max_per_strategy_trades=2,
        max_quantity_per_order=50,
        max_daily_loss=25000.0,
        allowed_symbols=["NIFTY", "BANKNIFTY"],
        allowed_segments=["NSEFO"],
    )
    return RiskManager(config=cfg, kill_switch=kill_switch, trade_manager=trade_manager)


@pytest.mark.asyncio
async def test_trading_disabled_rejects_signal():
    cfg = RiskConfig(trading_enabled=False)
    rm = _make_risk_manager(config=cfg)
    approved, reason = await rm.check_signal(_make_signal(), context={})
    assert not approved
    assert "disabled" in reason.lower()


@pytest.mark.asyncio
async def test_max_open_trades_exceeded():
    trade_manager = MagicMock()
    trade_manager.get_open_trade_count.return_value = 10
    trade_manager.get_open_trades.return_value = []
    rm = _make_risk_manager(trade_manager=trade_manager)
    approved, reason = await rm.check_signal(_make_signal(), context={})
    assert not approved
    assert "max open trades" in reason.lower()


@pytest.mark.asyncio
async def test_per_strategy_trades_exceeded():
    trade_manager = MagicMock()
    trade_manager.get_open_trade_count.return_value = 1
    trade_manager.get_open_trades.return_value = [
        {"strategy_name": "short_straddle"},
        {"strategy_name": "short_straddle"},
    ]
    rm = _make_risk_manager(trade_manager=trade_manager)
    approved, reason = await rm.check_signal(_make_signal(), context={})
    assert not approved
    assert "short_straddle" in reason


@pytest.mark.asyncio
async def test_max_quantity_exceeded():
    rm = _make_risk_manager()
    signal = _make_signal(quantity=100)
    approved, reason = await rm.check_signal(signal, context={})
    assert not approved
    assert "quantity" in reason.lower()


@pytest.mark.asyncio
async def test_daily_loss_limit_exceeded():
    rm = _make_risk_manager()
    rm._daily_loss = 25000.0
    rm._daily_loss_date = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).date().isoformat()
    approved, reason = await rm.check_signal(_make_signal(), context={})
    assert not approved
    assert "daily loss" in reason.lower()


@pytest.mark.asyncio
async def test_all_checks_pass():
    trade_manager = MagicMock()
    trade_manager.get_open_trade_count.return_value = 0
    trade_manager.get_open_trades.return_value = []
    rm = _make_risk_manager(trade_manager=trade_manager)
    approved, reason = await rm.check_signal(_make_signal(), context={})
    assert approved
    assert reason == "approved"


@pytest.mark.asyncio
async def test_kill_switch_active_rejects():
    event_bus = MagicMock()
    event_bus.publish = AsyncMock()
    kill_switch = KillSwitch(event_bus=event_bus)
    kill_switch._activated = True  # directly set without triggering squareoff
    rm = _make_risk_manager(kill_switch=kill_switch)
    approved, reason = await rm.check_signal(_make_signal(), context={})
    assert not approved
    assert "kill switch" in reason.lower()


def test_kill_switch_deactivation():
    event_bus = MagicMock()
    kill_switch = KillSwitch(event_bus=event_bus)
    kill_switch._activated = True
    kill_switch.deactivate()
    assert not kill_switch.is_activated


@pytest.mark.asyncio
async def test_disallowed_segment_rejected():
    rm = _make_risk_manager()
    signal = _make_signal(exchange_segment="BSE")
    approved, reason = await rm.check_signal(signal, context={})
    assert not approved
    assert "segment" in reason.lower()


@pytest.mark.asyncio
async def test_disallowed_symbol_rejected():
    rm = _make_risk_manager()
    signal = _make_signal(symbol="RELIANCE_CE")
    approved, reason = await rm.check_signal(signal, context={})
    assert not approved
    assert "symbol" in reason.lower()
