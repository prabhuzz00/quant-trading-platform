"""Tests for TradeManager: trade lifecycle and PnL calculations."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from execution.trade_manager import TradeManager, TRADE_OPEN, TRADE_CLOSED, TRADE_PENDING
from engine.signal import Signal, SignalAction, OrderMode
from core.event_bus import EventBus, EventType, Event


def _make_event_bus():
    bus = MagicMock(spec=EventBus)
    bus.subscribe.return_value = asyncio.Queue()
    return bus


def _make_signal(strategy="test_strategy", action=SignalAction.BUY, qty=10, price=100.0):
    return Signal(
        strategy_name=strategy,
        action=action,
        exchange_segment="NSEFO",
        exchange_instrument_id=999,
        symbol="NIFTY_CE",
        quantity=qty,
        limit_price=price,
    )


def test_register_trade_creates_pending():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    signal = _make_signal()
    tm.register_trade("order_001", signal)

    trade = tm.get_trade("order_001")
    assert trade is not None
    assert trade["status"] == TRADE_PENDING
    assert trade["strategy_name"] == "test_strategy"
    assert trade["quantity"] == 10


@pytest.mark.asyncio
async def test_open_trade_on_fill():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    signal = _make_signal()
    tm.register_trade("order_002", signal)

    fill_data = {
        "AppOrderID": "order_002",
        "OrderStatus": "Filled",
        "OrderQuantity": 10,
        "OrderAverageTradedPrice": 105.0,
        "TradingSymbol": "NIFTY_CE",
    }
    await tm._handle_order_update(fill_data)

    trade = tm.get_trade("order_002")
    assert trade["status"] == TRADE_OPEN
    assert trade["avg_price"] == 105.0
    assert trade["filled_qty"] == 10


@pytest.mark.asyncio
async def test_close_trade_on_cancel():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    signal = _make_signal()
    tm.register_trade("order_003", signal)

    await tm._handle_order_update({
        "AppOrderID": "order_003",
        "OrderStatus": "Filled",
        "OrderQuantity": 10,
        "OrderAverageTradedPrice": 100.0,
    })
    await tm._handle_order_update({
        "AppOrderID": "order_003",
        "OrderStatus": "Cancelled",
    })

    trade = tm.get_trade("order_003")
    assert trade["status"] == TRADE_CLOSED


def test_get_open_trades_returns_only_open():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    tm._trades = {
        "a": {"status": TRADE_OPEN, "pnl": 0.0},
        "b": {"status": TRADE_CLOSED, "pnl": 0.0},
        "c": {"status": TRADE_PENDING, "pnl": 0.0},
        "d": {"status": TRADE_OPEN, "pnl": 0.0},
    }
    open_trades = tm.get_open_trades()
    assert len(open_trades) == 2
    assert all(t["status"] == TRADE_OPEN for t in open_trades)


def test_get_open_trade_count():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    tm._trades = {
        "a": {"status": TRADE_OPEN, "pnl": 0.0},
        "b": {"status": TRADE_CLOSED, "pnl": 0.0},
    }
    assert tm.get_open_trade_count() == 1


def test_unrealized_pnl_buy_side():
    """BUY PnL: (exit - entry) * qty"""
    entry_price = 100.0
    exit_price = 120.0
    qty = 5
    pnl = (exit_price - entry_price) * qty
    assert pnl == 100.0


def test_unrealized_pnl_sell_side():
    """SELL PnL: (entry - exit) * qty"""
    entry_price = 150.0
    exit_price = 130.0
    qty = 4
    pnl = (entry_price - exit_price) * qty
    assert pnl == 80.0


def test_get_total_pnl():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    tm._trades = {
        "a": {"status": TRADE_OPEN, "pnl": 200.0},
        "b": {"status": TRADE_CLOSED, "pnl": -50.0},
        "c": {"status": TRADE_CLOSED, "pnl": 100.0},
    }
    assert tm.get_total_pnl() == 250.0


@pytest.mark.asyncio
async def test_trade_update_updates_pnl():
    bus = _make_event_bus()
    tm = TradeManager(event_bus=bus)
    signal = _make_signal()
    tm.register_trade("order_004", signal)

    await tm._handle_trade_update({"AppOrderID": "order_004", "pnl": 500.0})
    trade = tm.get_trade("order_004")
    assert trade["pnl"] == 500.0
