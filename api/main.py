"""FastAPI application entry point with lifespan management."""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.dependencies import app_state
from api.routes import dashboard, positions, risk, strategies, trades
from api.routes import manual_trading
from api.routes import regime as regime_route
from config.settings import settings
from core.candle_store import CandleStore
from core.event_bus import EventBus
from core.market_data_socket import MarketDataSocket
from core.order_socket import OrderSocket
from core.xts_client import XTSInteractiveClient, XTSMarketDataClient
from database.db import close_db, create_tables, init_db
from execution.order_manager import OrderManager
from execution.position_reconciler import PositionReconciler
from execution.trade_manager import TradeManager
from risk.kill_switch import KillSwitch
from risk.risk_config import RiskConfig
from risk.risk_manager import RiskManager
from strategies.bear_put_spread import BearPutSpread
from strategies.bull_call_spread import BullCallSpread
from strategies.butterfly_spread import ButterflySpread
from strategies.calendar_spread import CalendarSpread
from strategies.covered_call import CoveredCall
from strategies.iron_condor import IronCondor
from strategies.long_straddle import LongStraddle
from strategies.protective_put import ProtectivePut
from strategies.short_straddle import ShortStraddle
from strategies.short_strangle import ShortStrangle
from strategies.smc_confluence import SMCConfluenceStrategy
from strategies.volume_breakout import VolumeBreakoutStrategy
from strategies.indicator_regime_strategy import IndicatorRegimeStrategy
from strategies.strategy_registry import StrategyRegistry
from engine.instrument_manager import InstrumentManager
from engine.strategy_engine import StrategyEngine
from engine.warmup import WarmupService
from engine.auto_regime_engine import AutoRegimeEngine

logger = structlog.get_logger(__name__)


def _build_strategy_registry(candle_store: CandleStore) -> StrategyRegistry:
    registry = StrategyRegistry()
    # Multi-leg strategies (no historical data required)
    for cls in [
        IronCondor,
        ShortStraddle,
        ShortStrangle,
        BullCallSpread,
        BearPutSpread,
        LongStraddle,
        ButterflySpread,
        CalendarSpread,
        CoveredCall,
        ProtectivePut,
    ]:
        try:
            registry.register(cls())
        except (TypeError, ImportError, AttributeError) as exc:
            logger.warning("Failed to register strategy", cls=cls.__name__, error=str(exc))

    # Single-leg strategies that need historical candles
    for strategy in [
        SMCConfluenceStrategy(),
        VolumeBreakoutStrategy(),
        IndicatorRegimeStrategy(),
    ]:
        strategy.candle_store = candle_store
        try:
            registry.register(strategy)
        except (TypeError, ImportError, AttributeError) as exc:
            logger.warning("Failed to register strategy", cls=type(strategy).__name__, error=str(exc))

    return registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize all platform components on startup and clean up on shutdown."""
    logger.info("Starting trading platform API")

    # --- Database ---
    init_db(settings.database_url, echo=settings.debug)
    try:
        await create_tables()
    except Exception as exc:
        logger.error("Failed to create DB tables", error=str(exc))

    # --- Core infrastructure ---
    event_bus = EventBus()
    app_state["event_bus"] = event_bus

    # --- Redis (optional; used for candle cache) ---
    redis_client = None
    if settings.redis_url:
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await redis_client.ping()
            app_state["redis"] = redis_client
            logger.info("Redis connected", url=settings.redis_url)
        except Exception as exc:
            logger.warning("Redis connection failed – candle cache disabled", error=str(exc))
            redis_client = None

    # --- Candle store (shared across all strategies needing history) ---
    candle_store = CandleStore(
        redis_client=redis_client,
        cache_ttl=settings.candle_cache_ttl_seconds,
        max_size=settings.candle_max_store_size,
    )
    app_state["candle_store"] = candle_store

    # --- XTS clients ---
    xts_market_data = XTSMarketDataClient(
        url=settings.xts_market_data_url,
        app_key=settings.xts_market_data_key,
        secret_key=settings.xts_market_data_secret,
        source=settings.xts_market_data_source,
        verify_ssl=settings.xts_verify_ssl,
    )
    xts_interactive = XTSInteractiveClient(
        url=settings.xts_interactive_url,
        app_key=settings.xts_interactive_key,
        secret_key=settings.xts_interactive_secret,
        source=settings.xts_interactive_source,
        verify_ssl=settings.xts_verify_ssl,
        client_id=settings.xts_interactive_client_id,
    )
    app_state["xts_market_data"] = xts_market_data
    app_state["xts_interactive"] = xts_interactive

    # --- Instrument Manager (shared; used by manual trading & strategies) ---
    instrument_manager = InstrumentManager(xts_market_data)
    app_state["instrument_manager"] = instrument_manager

    # Attempt XTS login (non-fatal; platform still serves API without live data)
    md_token: str = ""
    md_user_id: str = ""
    interactive_token: str = ""
    interactive_user_id: str = ""

    if settings.xts_market_data_key:
        try:
            result = await xts_market_data.login()
            md_token = result.get("token", "")
            md_user_id = result.get("userID", "")
            logger.info("XTS Market Data logged in")
        except Exception as exc:
            logger.warning("XTS Market Data login failed", error=str(exc))

    if settings.xts_interactive_key:
        try:
            result = await xts_interactive.login()
            interactive_token = result.get("token", "")
            interactive_user_id = result.get("userID", "")
            logger.info("XTS Interactive logged in")
        except Exception as exc:
            logger.warning("XTS Interactive login failed", error=str(exc))

    # --- WebSocket connections ---
    market_data_socket: MarketDataSocket | None = None
    order_socket: OrderSocket | None = None

    if md_token:
        market_data_socket = MarketDataSocket(
            url=settings.xts_market_data_url,
            token=md_token,
            user_id=md_user_id,
            event_bus=event_bus,
        )
        try:
            await market_data_socket.connect()
        except Exception as exc:
            logger.warning("MarketDataSocket connect failed", error=str(exc))
            market_data_socket = None

    if interactive_token:
        order_socket = OrderSocket(
            url=settings.xts_interactive_url,
            token=interactive_token,
            user_id=interactive_user_id,
            event_bus=event_bus,
        )
        try:
            await order_socket.connect()
        except Exception as exc:
            logger.warning("OrderSocket connect failed", error=str(exc))
            order_socket = None

    app_state["market_data_socket"] = market_data_socket
    app_state["order_socket"] = order_socket

    # --- Risk layer ---
    risk_config = RiskConfig(
        max_capital=settings.default_max_capital,
        max_daily_loss=settings.default_max_daily_loss,
        max_open_trades=settings.default_max_open_trades,
    )
    kill_switch = KillSwitch(event_bus=event_bus)
    app_state["kill_switch"] = kill_switch

    trade_manager = TradeManager(event_bus=event_bus)
    await trade_manager.start()
    app_state["trade_manager"] = trade_manager

    risk_manager = RiskManager(
        config=risk_config,
        kill_switch=kill_switch,
        trade_manager=trade_manager,
    )
    app_state["risk_manager"] = risk_manager

    order_manager = OrderManager(
        event_bus=event_bus,
        xts_client=xts_interactive,
        risk_manager=risk_manager,
    )
    await order_manager.start()
    app_state["order_manager"] = order_manager

    # Wire kill switch -> order manager
    kill_switch.order_manager = order_manager

    # --- Strategy registry ---
    strategy_registry = _build_strategy_registry(candle_store)
    app_state["strategy_registry"] = strategy_registry

    # --- Historical candle warmup (non-fatal) ---
    if xts_market_data.token:
        warmup_service = WarmupService(
            xts_client=xts_market_data,
            candle_store=candle_store,
        )
        try:
            await warmup_service.warmup_strategies(strategy_registry.get_all_strategies())
        except Exception as exc:
            logger.warning("Historical candle warmup encountered an error", error=str(exc))

        # Explicitly warm up the regime detection instrument so that
        # AutoRegimeEngine always has sufficient XTS historical candles,
        # independent of which indicator-based strategies are registered.
        try:
            await warmup_service.warmup_instrument(
                exchange_segment=settings.regime_exchange_segment,
                instrument_id=settings.regime_instrument_id,
                timeframe=settings.regime_timeframe,
                n_candles=settings.regime_n_candles,
            )
        except Exception as exc:
            logger.warning(
                "Regime instrument historical warmup encountered an error",
                instrument_id=settings.regime_instrument_id,
                timeframe=settings.regime_timeframe,
                error=str(exc),
            )
    else:
        logger.info("Skipping historical candle warmup – XTS Market Data not authenticated")

    # --- Background tasks ---
    strategy_engine = StrategyEngine(
        event_bus=event_bus,
        strategy_registry=strategy_registry,
        candle_store=candle_store,
    )
    app_state["strategy_engine"] = strategy_engine
    engine_task = asyncio.create_task(strategy_engine.start(), name="strategy_engine")

    # --- AI Regime Engine ---
    regime_engine = AutoRegimeEngine(
        strategy_registry=strategy_registry,
        candle_store=candle_store,
        instrument_id=settings.regime_instrument_id,
        timeframe=settings.regime_timeframe,
        enabled=settings.regime_enabled,
        interval_minutes=settings.regime_interval_minutes,
        score_threshold=settings.regime_score_threshold,
    )
    app_state["regime_engine"] = regime_engine
    await regime_engine.start()

    position_reconciler = PositionReconciler(
        event_bus=event_bus,
        xts_client=xts_interactive,
        trade_manager=trade_manager,
    )
    await position_reconciler.start()
    app_state["position_reconciler"] = position_reconciler

    logger.info("Trading platform API started")

    yield  # Application is running

    # --- Shutdown ---
    logger.info("Shutting down trading platform API")

    await regime_engine.stop()
    await strategy_engine.stop()
    engine_task.cancel()
    try:
        await engine_task
    except asyncio.CancelledError:
        pass

    await position_reconciler.stop()
    await trade_manager.stop()
    await order_manager.stop()

    if market_data_socket:
        await market_data_socket.disconnect()
    if order_socket:
        await order_socket.disconnect()

    await xts_market_data.close()
    await xts_interactive.close()

    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass

    await close_db()
    logger.info("Trading platform API shut down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Quant Trading Platform API",
    version="1.0.0",
    description="REST API and WebSocket interface for the quant options trading platform",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(trades.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(manual_trading.router, prefix="/api")
app.include_router(regime_route.router, prefix="/api")
app.include_router(dashboard.router)  # WebSocket route mounts at /ws/dashboard


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check():
    """Simple liveness probe."""
    market_socket = app_state.get("market_data_socket")
    order_socket = app_state.get("order_socket")
    return {
        "status": "ok",
        "market_connected": market_socket.is_connected() if market_socket else False,
        "order_connected": order_socket.is_connected() if order_socket else False,
    }


# ---------------------------------------------------------------------------
# Global error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": type(exc).__name__},
    )
