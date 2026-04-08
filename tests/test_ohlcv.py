"""Tests for the OHLCV service and API routes."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.ohlcv_service import OHLCVService, _parse_ohlc_result


# ---------------------------------------------------------------------------
# _parse_ohlc_result tests
# ---------------------------------------------------------------------------


class TestParseOhlcResult:
    """Unit tests for the candle parser."""

    def test_pipe_separated_string(self):
        raw = "1609459200|19000.00|19050.00|18980.00|19020.00|1000000|0,1609459260|19020.00|19060.00|18990.00|19040.00|500000|0"
        candles = _parse_ohlc_result(raw)
        assert len(candles) == 2
        assert candles[0]["open"] == 19000.00
        assert candles[0]["high"] == 19050.00
        assert candles[0]["low"] == 18980.00
        assert candles[0]["close"] == 19020.00
        assert candles[0]["volume"] == 1000000.0
        assert isinstance(candles[0]["timestamp"], datetime)

    def test_pipe_separated_trailing_pipe(self):
        raw = "1609459200|100.0|110.0|90.0|105.0|500|0,"
        candles = _parse_ohlc_result(raw)
        assert len(candles) == 1

    def test_list_of_dicts_uppercase_keys(self):
        raw = [
            {"Time": 1609459200, "Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 500},
        ]
        candles = _parse_ohlc_result(raw)
        assert len(candles) == 1
        assert candles[0]["open"] == 100.0
        assert candles[0]["volume"] == 500.0

    def test_list_of_dicts_lowercase_keys(self):
        raw = [
            {"time": 1609459200, "open": 200, "high": 210, "low": 190, "close": 205, "volume": 1000},
        ]
        candles = _parse_ohlc_result(raw)
        assert len(candles) == 1
        assert candles[0]["close"] == 205.0

    def test_empty_string_returns_empty_list(self):
        assert _parse_ohlc_result("") == []

    def test_empty_list_returns_empty_list(self):
        assert _parse_ohlc_result([]) == []

    def test_malformed_string_entries_skipped(self):
        raw = "bad_data,1609459200|100.0|110.0|90.0|105.0|500|0"
        candles = _parse_ohlc_result(raw)
        assert len(candles) == 1

    def test_missing_volume_defaults_to_zero(self):
        raw = "1609459200|100.0|110.0|90.0|105.0"
        candles = _parse_ohlc_result(raw)
        assert len(candles) == 1
        assert candles[0]["volume"] == 0.0


# ---------------------------------------------------------------------------
# OHLCVService.fetch_and_store tests
# ---------------------------------------------------------------------------


class TestOHLCVServiceFetchAndStore:
    """Tests for fetch_and_store with mocked XTS client and DB."""

    @pytest.fixture
    def mock_xts_client(self):
        client = AsyncMock()
        client.token = "test-token"
        return client

    @pytest.mark.asyncio
    async def test_fetch_and_store_returns_count(self, mock_xts_client):
        """Successful XTS response produces upserted count."""
        mock_xts_client.get_ohlc.return_value = {
            "type": "success",
            "result": {
                "dataReponse": "1609459200|100.0|110.0|90.0|105.0|500|0,1609459260|105.0|115.0|95.0|110.0|600|0"
            },
        }

        service = OHLCVService(mock_xts_client)
        with patch.object(service, "_upsert_candles", new_callable=AsyncMock, return_value=2):
            count = await service.fetch_and_store()
        assert count == 2

    @pytest.mark.asyncio
    async def test_fetch_and_store_no_candles(self, mock_xts_client):
        """Empty result from XTS returns 0."""
        mock_xts_client.get_ohlc.return_value = {"result": {"dataReponse": ""}}
        service = OHLCVService(mock_xts_client)
        count = await service.fetch_and_store()
        assert count == 0

    @pytest.mark.asyncio
    async def test_fetch_and_store_calls_xts_api(self, mock_xts_client):
        """Verify the XTS client is called with the correct parameters."""
        mock_xts_client.get_ohlc.return_value = {"result": {"dataReponse": ""}}
        service = OHLCVService(mock_xts_client)
        await service.fetch_and_store(
            exchange_segment="NSECM",
            exchange_instrument_id=26000,
            timeframe=5,
        )
        mock_xts_client.get_ohlc.assert_called_once()
        call_kwargs = mock_xts_client.get_ohlc.call_args
        assert call_kwargs.kwargs["exchange_instrument_id"] == 26000
        assert call_kwargs.kwargs["compression_value"] == 300  # 5 min × 60 s/min


# ---------------------------------------------------------------------------
# Pydantic schema tests
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_ohlcv_fetch_request_defaults(self):
        from api.schemas import OHLCVFetchRequest
        req = OHLCVFetchRequest()
        assert req.exchange_segment == "NSECM"
        assert req.exchange_instrument_id == 26000
        assert req.symbol == "NIFTY 50"
        assert req.timeframe == 1
        assert req.lookback_days == 5

    def test_ohlcv_record_from_attributes(self):
        from api.schemas import OHLCVRecord

        class FakeRow:
            id = 1
            exchange_segment = "NSECM"
            exchange_instrument_id = 26000
            symbol = "NIFTY 50"
            timeframe = 1
            timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
            open = 100.0
            high = 110.0
            low = 90.0
            close = 105.0
            volume = 500.0
            created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        record = OHLCVRecord.model_validate(FakeRow(), from_attributes=True)
        assert record.symbol == "NIFTY 50"
        assert record.close == 105.0
