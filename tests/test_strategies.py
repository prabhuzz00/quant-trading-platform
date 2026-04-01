"""Tests for strategy signal generation."""
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from strategies.short_straddle import ShortStraddle
from engine.signal import SignalAction


def _make_instruments():
    ce_instr = {"ExchangeInstrumentID": 1001, "Name": "NIFTY_CE"}
    pe_instr = {"ExchangeInstrumentID": 1002, "Name": "NIFTY_PE"}
    return ce_instr, pe_instr


def _make_strategy_with_instruments():
    ce_instr, pe_instr = _make_instruments()
    im = MagicMock()
    im.get_nearest_expiry = AsyncMock(return_value="2024-01-25")
    im.get_atm_strike = MagicMock(return_value=21000)
    im.get_option_instrument = AsyncMock(side_effect=[ce_instr, pe_instr])
    im.get_ltp = MagicMock(side_effect=lambda instrument_id: 100.0 if instrument_id == 1001 else 95.0)

    strat = ShortStraddle(
        name="short_straddle",
        instrument_manager=im,
        symbol="NIFTY",
        exchange_segment="NSEFO",
        quantity=1,
        enabled=True,
    )
    strat._ce_instrument = ce_instr
    strat._pe_instrument = pe_instr
    return strat


@pytest.mark.asyncio
async def test_short_straddle_emits_signals_when_no_position():
    strat = _make_strategy_with_instruments()

    trading_time = datetime(2024, 1, 25, 10, 0, 0)  # 10:00 AM IST
    with patch("strategies.short_straddle.datetime") as mock_dt:
        mock_dt.now.return_value = trading_time
        signals = await strat.on_tick({"ltp": 21000.0})

    assert len(signals) == 2
    assert all(s.action == SignalAction.SELL for s in signals)
    assert all(s.strategy_name == "short_straddle" for s in signals)
    symbols = {s.symbol for s in signals}
    assert "NIFTY_CE" in symbols
    assert "NIFTY_PE" in symbols


@pytest.mark.asyncio
async def test_short_straddle_no_signal_when_position_open():
    strat = _make_strategy_with_instruments()
    strat._position_open = True

    signals = await strat.on_tick({"ltp": 21000.0})
    assert signals == []


@pytest.mark.asyncio
async def test_short_straddle_no_signal_when_disabled():
    strat = _make_strategy_with_instruments()
    strat.enabled = False

    signals = await strat.on_tick({"ltp": 21000.0})
    assert signals == []


@pytest.mark.asyncio
async def test_short_straddle_no_signal_outside_trading_hours():
    strat = _make_strategy_with_instruments()

    # Before market open: 8:00 AM IST
    before_open = datetime(2024, 1, 25, 8, 0, 0)
    with patch("strategies.short_straddle.datetime") as mock_dt:
        mock_dt.now.return_value = before_open
        signals = await strat.on_tick({"ltp": 21000.0})
    assert signals == []

    # After market close: 15:30 IST
    after_close = datetime(2024, 1, 25, 15, 30, 0)
    with patch("strategies.short_straddle.datetime") as mock_dt:
        mock_dt.now.return_value = after_close
        signals = await strat.on_tick({"ltp": 21000.0})
    assert signals == []


@pytest.mark.asyncio
async def test_short_straddle_signal_has_correct_fields():
    strat = _make_strategy_with_instruments()

    trading_time = datetime(2024, 1, 25, 11, 30, 0)
    with patch("strategies.short_straddle.datetime") as mock_dt:
        mock_dt.now.return_value = trading_time
        signals = await strat.on_tick({"ltp": 21000.0})

    assert len(signals) == 2
    for s in signals:
        assert s.quantity == 1
        assert s.exchange_segment == "NSEFO"
        assert s.strategy_name == "short_straddle"
        assert s.limit_price > 0
        assert s.stoploss_points > 0
        assert s.target_points > 0


@pytest.mark.asyncio
async def test_short_straddle_sets_position_open_after_signal():
    strat = _make_strategy_with_instruments()

    trading_time = datetime(2024, 1, 25, 10, 0, 0)
    with patch("strategies.short_straddle.datetime") as mock_dt:
        mock_dt.now.return_value = trading_time
        await strat.on_tick({"ltp": 21000.0})

    assert strat._position_open is True
