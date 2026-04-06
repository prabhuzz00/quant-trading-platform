"""Tests for historical candle fetching, live candle subscription, regime
detection pipeline, and the combined historical+live data flow."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.candle_store import Candle, CandleStore
from core.event_bus import EventBus, Event, EventType
from core.market_data_socket import MarketDataSocket
from engine.auto_regime_engine import AutoRegimeEngine
from engine.regime_detector import RegimeDetector, RegimeType
from engine.strategy_engine import StrategyEngine
from strategies.strategy_registry import StrategyRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candle(i: int, base_price: float = 19000.0) -> Candle:
    """Create a synthetic candle with incrementing timestamps."""
    return Candle(
        timestamp=datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i * 5),
        open=base_price + i,
        high=base_price + i + 10,
        low=base_price + i - 5,
        close=base_price + i + 5,
        volume=100_000 + i * 100,
    )


def _make_candles(n: int, base_price: float = 19000.0):
    """Generate *n* synthetic candles."""
    return [_make_candle(i, base_price) for i in range(n)]


# ---------------------------------------------------------------------------
# CandleStore basic behaviour
# ---------------------------------------------------------------------------

class TestCandleStore:

    def test_add_and_get_candles(self):
        store = CandleStore(max_size=500)
        candles = _make_candles(10)
        for c in candles:
            store.add_candle(26000, 5, c)
        assert store.candle_count(26000, 5) == 10
        retrieved = store.get_candles(26000, 5)
        assert len(retrieved) == 10
        assert retrieved[0].timestamp < retrieved[-1].timestamp

    def test_get_candles_with_limit(self):
        store = CandleStore(max_size=500)
        for c in _make_candles(20):
            store.add_candle(26000, 5, c)
        last5 = store.get_candles(26000, 5, n=5)
        assert len(last5) == 5

    def test_max_size_eviction(self):
        store = CandleStore(max_size=10)
        for c in _make_candles(15):
            store.add_candle(26000, 5, c)
        assert store.candle_count(26000, 5) == 10

    def test_is_warmed_up(self):
        store = CandleStore(max_size=500)
        assert not store.is_warmed_up(26000, 5, 60)
        for c in _make_candles(60):
            store.add_candle(26000, 5, c)
        assert store.is_warmed_up(26000, 5, 60)


# ---------------------------------------------------------------------------
# MarketDataSocket.is_connected and subscribe_candles
# ---------------------------------------------------------------------------

class TestMarketDataSocket:

    def test_is_connected_is_callable(self):
        """is_connected must be a regular method (not a @property)."""
        event_bus = EventBus()
        sock = MarketDataSocket(
            url="https://example.com", token="t", user_id="u",
            event_bus=event_bus,
        )
        # Must be callable with ()
        result = sock.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_candles_calls_xts_client(self):
        """subscribe_candles should call xts_client.subscribe with code 1505."""
        event_bus = EventBus()
        mock_client = MagicMock()
        mock_client.subscribe = AsyncMock(return_value={"type": "success"})

        sock = MarketDataSocket(
            url="https://example.com", token="t", user_id="u",
            event_bus=event_bus, xts_client=mock_client,
        )
        instruments = [{"exchangeSegment": 1, "exchangeInstrumentID": 26000}]
        await sock.subscribe_candles(instruments)

        mock_client.subscribe.assert_called_once_with(
            instruments=instruments,
            xts_message_code=1505,
        )

    @pytest.mark.asyncio
    async def test_subscribe_candles_without_client(self):
        """subscribe_candles should not raise when xts_client is None."""
        event_bus = EventBus()
        sock = MarketDataSocket(
            url="https://example.com", token="t", user_id="u",
            event_bus=event_bus, xts_client=None,
        )
        # Should not raise
        await sock.subscribe_candles([{"exchangeSegment": 1, "exchangeInstrumentID": 26000}])

    @pytest.mark.asyncio
    async def test_subscribe_candles_empty_list(self):
        """subscribe_candles with empty instruments list is a no-op."""
        event_bus = EventBus()
        mock_client = MagicMock()
        mock_client.subscribe = AsyncMock()
        sock = MarketDataSocket(
            url="https://example.com", token="t", user_id="u",
            event_bus=event_bus, xts_client=mock_client,
        )
        await sock.subscribe_candles([])
        mock_client.subscribe.assert_not_called()


# ---------------------------------------------------------------------------
# StrategyEngine: bar ingestion
# ---------------------------------------------------------------------------

class TestStrategyEngineBarIngestion:

    def test_ingest_bar_adds_candle_to_store(self):
        """_ingest_bar should parse the XTS payload and add to CandleStore."""
        event_bus = EventBus()
        registry = StrategyRegistry()
        store = CandleStore(max_size=500)
        engine = StrategyEngine(
            event_bus=event_bus,
            strategy_registry=registry,
            candle_store=store,
        )
        payload = {
            "ExchangeInstrumentID": 26000,
            "ExchangeSegment": 1,
            "Open": 19000.0,
            "High": 19050.0,
            "Low": 18980.0,
            "Close": 19020.0,
            "Volume": 100000,
            "Time": 1609459200,
            "CompressionValue": 5,
        }
        engine._ingest_bar(payload)
        assert store.candle_count(26000, 5) == 1
        candle = store.get_candles(26000, 5)[0]
        assert candle.open == 19000.0
        assert candle.close == 19020.0
        assert candle.volume == 100000

    def test_ingest_bar_defaults_to_1min_when_no_compression(self):
        """When CompressionValue is missing, default to timeframe 1."""
        store = CandleStore(max_size=500)
        engine = StrategyEngine(
            event_bus=EventBus(),
            strategy_registry=StrategyRegistry(),
            candle_store=store,
        )
        payload = {
            "ExchangeInstrumentID": 26000,
            "Open": 19000.0,
            "High": 19050.0,
            "Low": 18980.0,
            "Close": 19020.0,
            "Volume": 100000,
            "Time": 1609459200,
        }
        engine._ingest_bar(payload)
        assert store.candle_count(26000, 1) == 1


# ---------------------------------------------------------------------------
# RegimeDetector
# ---------------------------------------------------------------------------

class TestRegimeDetector:

    def test_insufficient_candles_returns_unknown(self):
        detector = RegimeDetector(min_candles=60)
        candles = _make_candles(10)
        result = detector.detect(candles)
        assert result.regime_type == RegimeType.UNKNOWN

    def test_sufficient_candles_returns_known_regime(self):
        detector = RegimeDetector(min_candles=60)
        # Create trending bullish data: monotonically increasing prices
        candles = _make_candles(80, base_price=18000.0)
        result = detector.detect(candles)
        assert result.regime_type != RegimeType.UNKNOWN
        assert result.candle_count == 80

    def test_trending_bullish_detection(self):
        """Monotonically increasing prices should produce a bullish trend."""
        detector = RegimeDetector(min_candles=60)
        candles = []
        for i in range(80):
            candles.append(Candle(
                timestamp=datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i * 5),
                open=18000.0 + i * 10,
                high=18000.0 + i * 10 + 15,
                low=18000.0 + i * 10 - 5,
                close=18000.0 + i * 10 + 10,
                volume=100_000,
            ))
        result = detector.detect(candles)
        assert result.trend == "bullish"


# ---------------------------------------------------------------------------
# AutoRegimeEngine: combined historical + live data
# ---------------------------------------------------------------------------

class TestAutoRegimeEngine:

    @pytest.mark.asyncio
    async def test_analyze_uses_candle_store_when_sufficient(self):
        """When CandleStore has enough candles, no fallback is needed."""
        registry = StrategyRegistry()
        store = CandleStore(max_size=500)
        # Fill with 80 candles (above the 60 min_candles threshold)
        for c in _make_candles(80):
            store.add_candle(26000, 5, c)

        engine = AutoRegimeEngine(
            strategy_registry=registry,
            candle_store=store,
            instrument_id=26000,
            timeframe=5,
            enabled=False,
        )
        result = await engine.analyze_and_apply()
        assert result.regime.regime_type != RegimeType.UNKNOWN
        assert result.error is None

    @pytest.mark.asyncio
    async def test_analyze_falls_back_to_api(self):
        """When CandleStore and DB are empty, engine should try XTS API."""
        registry = StrategyRegistry()
        store = CandleStore(max_size=500)
        # CandleStore is empty → should try DB then API

        # Create a mock XTS client that returns historical candles
        mock_xts = MagicMock()
        mock_xts.token = "test_token"

        # Build a pipe-separated candle string with 120 candles
        candle_parts = []
        base_ts = int(datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc).timestamp())
        for i in range(120):
            ts = base_ts + i * 300  # 5-minute intervals
            price = 19000 + i
            candle_parts.append(
                f"{ts},{price},{price+10},{price-5},{price+5},100000"
            )
        ohlc_result = "|".join(candle_parts)
        mock_xts.get_ohlc = AsyncMock(return_value={"result": ohlc_result})

        engine = AutoRegimeEngine(
            strategy_registry=registry,
            candle_store=store,
            instrument_id=26000,
            timeframe=5,
            enabled=False,
            xts_client=mock_xts,
            exchange_segment="NSECM",
        )

        # Patch the DB fallback to return empty (simulating empty DB)
        with patch.object(engine, '_fetch_candles_from_db', new_callable=AsyncMock, return_value=[]):
            result = await engine.analyze_and_apply()

        # The API should have been called
        mock_xts.get_ohlc.assert_called_once()
        # Should detect a regime from the API-fetched candles
        assert result.regime.regime_type != RegimeType.UNKNOWN
        assert result.error is None
        # CandleStore should now be populated
        assert store.candle_count(26000, 5) > 0

    @pytest.mark.asyncio
    async def test_analyze_without_xts_client_returns_unknown(self):
        """Without XTS client and no candles, result should be UNKNOWN."""
        registry = StrategyRegistry()
        store = CandleStore(max_size=500)

        engine = AutoRegimeEngine(
            strategy_registry=registry,
            candle_store=store,
            instrument_id=26000,
            timeframe=5,
            enabled=False,
            xts_client=None,
        )

        with patch.object(engine, '_fetch_candles_from_db', new_callable=AsyncMock, return_value=[]):
            result = await engine.analyze_and_apply()

        assert result.regime.regime_type == RegimeType.UNKNOWN

    @pytest.mark.asyncio
    async def test_enabled_regime_toggles_strategies(self):
        """When enabled, regime engine should toggle strategies based on score."""
        registry = StrategyRegistry()

        # Create a mock strategy
        mock_strategy = MagicMock()
        mock_strategy.name = "smc_confluence"
        mock_strategy.enabled = False
        registry.register(mock_strategy)

        store = CandleStore(max_size=500)
        # Create strongly bullish candles (smc_confluence scores 90 for TRENDING_BULLISH)
        for i in range(80):
            store.add_candle(26000, 5, Candle(
                timestamp=datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=i * 5),
                open=18000.0 + i * 10,
                high=18000.0 + i * 10 + 15,
                low=18000.0 + i * 10 - 5,
                close=18000.0 + i * 10 + 10,
                volume=100_000,
            ))

        engine = AutoRegimeEngine(
            strategy_registry=registry,
            candle_store=store,
            instrument_id=26000,
            timeframe=5,
            enabled=True,  # Auto-toggle enabled
            score_threshold=80,
        )

        result = await engine.analyze_and_apply()
        assert result.error is None
        # In a bullish regime, smc_confluence should score 90 → enabled
        if result.regime.trend == "bullish":
            assert "smc_confluence" in result.enabled_by_regime


# ---------------------------------------------------------------------------
# OrderSocket.is_connected
# ---------------------------------------------------------------------------

class TestOrderSocket:

    def test_is_connected_is_callable(self):
        """is_connected must be a regular method (not a @property)."""
        from core.order_socket import OrderSocket
        event_bus = EventBus()
        sock = OrderSocket(
            url="https://example.com", token="t", user_id="u",
            event_bus=event_bus,
        )
        result = sock.is_connected()
        assert result is False
