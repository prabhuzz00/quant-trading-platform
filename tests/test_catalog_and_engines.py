"""Tests for the strategy catalog, Greeks calculator, backtester, and payoff engine."""

import math
import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from strategies.catalog import (
    get_all_strategies,
    get_strategy_by_id,
    get_categories,
    get_strategies_by_category,
    search_strategies,
    Category,
)
from engine.greeks import black_scholes, implied_volatility, compute_strategy_greeks
from engine.backtester import run_backtest
from engine.payoff import compute_payoff


# ---------------------------------------------------------------------------
# Strategy Catalog Tests
# ---------------------------------------------------------------------------

class TestStrategyCatalog:
    def test_catalog_has_77_strategies(self):
        all_strats = get_all_strategies()
        assert len(all_strats) == 77

    def test_get_strategy_by_id(self):
        s = get_strategy_by_id("iron_condor")
        assert s is not None
        assert s.name == "Iron Condor"
        assert s.category == Category.THETA

    def test_get_strategy_by_id_not_found(self):
        assert get_strategy_by_id("nonexistent") is None

    def test_categories_cover_all_strategies(self):
        groups = get_categories()
        total = sum(len(strats) for strats in groups.values())
        assert total == 77

    def test_search_bullish(self):
        results = search_strategies("bullish")
        assert len(results) > 0
        # All results should have 'bullish' in name, description, or tags
        for s in results:
            text = (s.name + s.description + " ".join(s.tags)).lower()
            assert "bullish" in text

    def test_search_iron_condor(self):
        results = search_strategies("iron condor")
        assert any(s.id == "iron_condor" for s in results)

    def test_all_strategies_have_required_fields(self):
        for s in get_all_strategies():
            assert s.id, f"Strategy missing id"
            assert s.name, f"Strategy {s.id} missing name"
            assert s.category, f"Strategy {s.id} missing category"
            assert s.description, f"Strategy {s.id} missing description"
            assert s.risk_level in ("Low", "Medium", "High"), \
                f"Strategy {s.id} has invalid risk_level: {s.risk_level}"

    def test_directional_category(self):
        strats = get_strategies_by_category(Category.DIRECTIONAL)
        assert len(strats) == 3

    def test_theta_category(self):
        strats = get_strategies_by_category(Category.THETA)
        assert len(strats) == 10

    def test_gamma_category(self):
        strats = get_strategies_by_category(Category.GAMMA)
        assert len(strats) == 11


# ---------------------------------------------------------------------------
# Greeks Calculator Tests
# ---------------------------------------------------------------------------

class TestGreeksCalculator:
    def test_atm_call_price(self):
        result = black_scholes(spot=100, strike=100, tte=1.0, iv=0.20, rate=0.05, is_call=True)
        # ATM call with 20% vol, 1 year: price should be roughly 10
        assert 8 < result.price < 14
        # Delta should be around 0.5 for ATM call
        assert 0.4 < result.delta < 0.7

    def test_atm_put_price(self):
        result = black_scholes(spot=100, strike=100, tte=1.0, iv=0.20, rate=0.05, is_call=False)
        # ATM put
        assert 4 < result.price < 10
        # Delta should be negative for puts
        assert -0.7 < result.delta < -0.3

    def test_deep_itm_call_delta_near_one(self):
        result = black_scholes(spot=100, strike=50, tte=0.5, iv=0.20, rate=0.05, is_call=True)
        assert result.delta > 0.95

    def test_deep_otm_call_delta_near_zero(self):
        result = black_scholes(spot=100, strike=200, tte=0.5, iv=0.20, rate=0.05, is_call=True)
        assert result.delta < 0.05

    def test_put_call_parity(self):
        spot, strike, tte, iv, rate = 100, 100, 1.0, 0.20, 0.05
        call = black_scholes(spot, strike, tte, iv, rate, is_call=True)
        put = black_scholes(spot, strike, tte, iv, rate, is_call=False)
        # Put-Call Parity: C - P = S - K * e^(-rT)
        lhs = call.price - put.price
        rhs = spot - strike * math.exp(-rate * tte)
        assert abs(lhs - rhs) < 0.01

    def test_theta_is_negative_for_long_options(self):
        call = black_scholes(spot=100, strike=100, tte=0.1, iv=0.20, rate=0.05, is_call=True)
        assert call.theta < 0  # Time decay hurts long positions

    def test_gamma_is_positive(self):
        result = black_scholes(spot=100, strike=100, tte=0.5, iv=0.20, rate=0.05, is_call=True)
        assert result.gamma > 0

    def test_vega_is_positive(self):
        result = black_scholes(spot=100, strike=100, tte=0.5, iv=0.20, rate=0.05, is_call=True)
        assert result.vega > 0

    def test_expired_option_returns_intrinsic(self):
        result = black_scholes(spot=110, strike=100, tte=0, iv=0.20, rate=0.05, is_call=True)
        assert result.price == 10.0
        assert result.gamma == 0.0

    def test_implied_volatility_solver(self):
        # First compute a price, then back-solve for IV
        original_iv = 0.25
        result = black_scholes(spot=100, strike=100, tte=0.5, iv=original_iv, rate=0.05, is_call=True)
        solved_iv = implied_volatility(
            market_price=result.price, spot=100, strike=100, tte=0.5, rate=0.05, is_call=True,
        )
        assert abs(solved_iv - original_iv) < 0.001

    def test_strategy_greeks_iron_condor(self):
        result = compute_strategy_greeks(
            spot=22000,
            strikes=[22100, 22200, 21900, 21800],
            option_types=["CE", "CE", "PE", "PE"],
            actions=["SELL", "BUY", "SELL", "BUY"],
            quantities=[1, 1, 1, 1],
            tte=7 / 365,
            iv=0.15,
        )
        # Iron condor should have positive theta (premium seller)
        assert result.net_theta > 0
        # Delta should be near zero (market neutral)
        assert abs(result.net_delta) < 0.5
        assert len(result.legs) == 4


# ---------------------------------------------------------------------------
# Backtester Tests
# ---------------------------------------------------------------------------

class TestBacktester:
    def test_basic_backtest(self):
        result = run_backtest(
            strategy_id="test_straddle",
            strategy_name="Test Straddle",
            legs_config=[
                {"option_type": "CE", "action": "SELL", "strike_offset": 0, "quantity": 1},
                {"option_type": "PE", "action": "SELL", "strike_offset": 0, "quantity": 1},
            ],
            spot=22000,
            iv=0.15,
            hold_days=7,
            num_trades=20,
        )
        assert result.total_trades == 20
        assert result.winning_trades + result.losing_trades == 20
        assert 0 <= result.win_rate <= 100
        assert len(result.equity_curve) == 20
        assert len(result.trades) == 20

    def test_backtest_sharpe_is_finite(self):
        result = run_backtest(
            strategy_id="test",
            strategy_name="Test",
            legs_config=[
                {"option_type": "CE", "action": "BUY", "strike_offset": 100, "quantity": 1},
            ],
            num_trades=30,
        )
        assert math.isfinite(result.sharpe_ratio)

    def test_backtest_equity_curve_monotonic_dates(self):
        result = run_backtest(
            strategy_id="test",
            strategy_name="Test",
            legs_config=[
                {"option_type": "CE", "action": "SELL", "strike_offset": 100, "quantity": 1},
                {"option_type": "CE", "action": "BUY", "strike_offset": 200, "quantity": 1},
            ],
            num_trades=10,
        )
        dates = [ec["date"] for ec in result.equity_curve]
        assert dates == sorted(dates)

    def test_backtest_monthly_pnl_sums_to_total(self):
        result = run_backtest(
            strategy_id="test",
            strategy_name="Test",
            legs_config=[
                {"option_type": "PE", "action": "SELL", "strike_offset": -100, "quantity": 1},
            ],
            num_trades=20,
        )
        monthly_sum = sum(m["pnl"] for m in result.monthly_pnl)
        assert abs(monthly_sum - result.total_pnl) < 0.1


# ---------------------------------------------------------------------------
# Payoff Engine Tests
# ---------------------------------------------------------------------------

class TestPayoffEngine:
    def test_bull_call_spread_payoff(self):
        result = compute_payoff(
            strategy_id="bcs",
            strategy_name="Bull Call Spread",
            spot=100,
            legs=[
                {"option_type": "CE", "action": "BUY", "strike": 100, "quantity": 1},
                {"option_type": "CE", "action": "SELL", "strike": 110, "quantity": 1},
            ],
            iv=0.20,
        )
        # Should have breakevens
        assert len(result.breakevens) >= 1
        # Max profit should be positive, max loss negative
        assert result.max_profit > 0
        assert result.max_loss < 0
        # Should have multiple curves
        assert len(result.curves) == 5  # [0, 3, 7, 14, 30]

    def test_payoff_expiry_curve_exists(self):
        result = compute_payoff(
            strategy_id="test",
            strategy_name="Test",
            spot=100,
            legs=[
                {"option_type": "CE", "action": "BUY", "strike": 100, "quantity": 1},
            ],
            iv=0.20,
            dte_values=[0, 7],
        )
        expiry_curve = [c for c in result.curves if c.dte == 0]
        assert len(expiry_curve) == 1
        assert len(expiry_curve[0].points) == 100  # default num_points

    def test_payoff_net_premium_sign(self):
        # Buying a call: net_premium is positive (entry cost to buyer)
        result = compute_payoff(
            strategy_id="test",
            strategy_name="Test",
            spot=100,
            legs=[
                {"option_type": "CE", "action": "BUY", "strike": 100, "quantity": 1},
            ],
            iv=0.20,
        )
        assert result.net_premium > 0  # Buyer pays premium (positive entry cost)


# ---------------------------------------------------------------------------
# API Route Tests
# ---------------------------------------------------------------------------

def _build_catalog_test_app():
    """Build a minimal app with catalog routes for testing."""
    from api.routes.strategy_catalog import router as catalog_router
    from api.routes.backtest import router as backtest_router
    from api.routes.payoff import router as payoff_router

    app = FastAPI()
    app.include_router(catalog_router, prefix="/api")
    app.include_router(backtest_router, prefix="/api")
    app.include_router(payoff_router, prefix="/api")
    return app


@pytest.fixture
def catalog_app():
    return _build_catalog_test_app()


@pytest.mark.asyncio
async def test_list_strategies_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.get("/api/strategies/list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 77


@pytest.mark.asyncio
async def test_categories_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.get("/api/strategies/categories")
    assert resp.status_code == 200
    data = resp.json()
    total = sum(c["count"] for c in data)
    assert total == 77


@pytest.mark.asyncio
async def test_search_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.get("/api/strategies/search", params={"q": "iron condor"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0


@pytest.mark.asyncio
async def test_strategy_detail_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.get("/api/strategies/detail/iron_condor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "iron_condor"
    assert data["name"] == "Iron Condor"


@pytest.mark.asyncio
async def test_strategy_detail_404(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.get("/api/strategies/detail/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_build_strategy_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.post("/api/strategies/build", json={
            "strategy_id": "iron_condor",
            "spot": 22000,
            "tte": 0.019,
            "iv": 0.15,
            "lot_size": 50,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == "iron_condor"
    assert len(data["legs"]) == 4


@pytest.mark.asyncio
async def test_option_price_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.post("/api/strategies/option-price", json={
            "spot": 22000,
            "strike": 22000,
            "tte": 0.019,
            "iv": 0.15,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] > 0
    assert "delta" in data


@pytest.mark.asyncio
async def test_implied_volatility_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.post("/api/strategies/implied-volatility", json={
            "market_price": 200,
            "spot": 22000,
            "strike": 22000,
            "tte": 0.019,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["implied_volatility"] > 0


@pytest.mark.asyncio
async def test_backtest_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test", timeout=30) as client:
        resp = await client.post("/api/backtest", json={
            "strategy_id": "iron_condor",
            "spot": 22000,
            "iv": 0.15,
            "hold_days": 7,
            "num_trades": 10,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_trades"] == 10
    assert "equity_curve" in data
    assert "trades" in data


@pytest.mark.asyncio
async def test_backtest_compare_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test", timeout=30) as client:
        resp = await client.post("/api/backtest/compare", json={
            "strategy_ids": ["iron_condor", "short_straddle"],
            "spot": 22000,
            "num_trades": 10,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rankings"]) == 2


@pytest.mark.asyncio
async def test_payoff_api(catalog_app):
    async with AsyncClient(transport=ASGITransport(app=catalog_app), base_url="http://test") as client:
        resp = await client.post("/api/payoff", json={
            "strategy_id": "bull_call_spread",
            "spot": 22000,
            "iv": 0.15,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "curves" in data
    assert len(data["curves"]) > 0
    assert "breakevens" in data
