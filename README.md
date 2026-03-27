# Quant Trading Platform

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

An automated options trading platform for Indian markets (NSE/BSE) built on the **Symphony Fintech XTS API**. It runs 10 configurable options strategies with real-time risk management, bracket/cover orders, a live React dashboard, and a REST API.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Trading Platform                         │
│                                                                 │
│  Market Data (XTS)                                              │
│       │                                                         │
│       ▼                                                         │
│  MarketDataSocket ──► Event Bus ──► Strategy Engine             │
│                           │              │                      │
│                           │         (10 Strategies)             │
│                           │              │                      │
│                           │         Signals ▼                   │
│                           │       Risk Manager                  │
│                           │    (pre-trade checks)               │
│                           │              │                      │
│                           │       Order Manager                 │
│                           │              │                      │
│                           │         XTS Interactive API         │
│                           │              │                      │
│                           ▼         OrderSocket                 │
│                     Trade Manager ◄──────┘                      │
│                     (P&L tracking)                              │
│                           │                                     │
│                      REST API / WebSocket Dashboard             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

- **10 options strategies**: Short Straddle, Short Strangle, Iron Condor, Bull Call Spread, Bear Put Spread, Long Straddle, Butterfly Spread, Calendar Spread, Covered Call, Protective Put
- **Real-time React dashboard** with live P&L, open trades, and risk metrics via WebSocket
- **Bracket & cover orders** with automatic stop-loss and target management
- **Pre-trade risk engine**: daily loss limit, max open trades, per-strategy limits, symbol/segment allowlists, kill switch
- **Async event-driven core** using asyncio + EventBus
- **PostgreSQL persistence** via SQLAlchemy async + Alembic migrations
- **Redis** for caching (optional)
- **Docker Compose** for one-command deployment
- **REST API** with full OpenAPI docs at `/docs`
- **ATM strike auto-selection** using live spot prices and instrument manager

---

## Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Python | 3.11 |
| Node.js | 18 |
| PostgreSQL | 14 |
| Redis | 6 (optional) |
| Docker & Docker Compose | 24 (for Docker deployment) |

You also need **XTS API credentials** from Symphony Fintech (see [XTS API Credentials](#xts-api-credentials)).

---

## Environment Setup

```bash
git clone https://github.com/your-org/quant-trading-platform.git
cd quant-trading-platform

# Copy and edit the environment file
cp .env.example .env
```

Edit `.env` with your credentials:

```dotenv
# XTS Market Data
XTS_MARKET_DATA_URL=https://developers.symphonyfintech.in
XTS_MARKET_DATA_KEY=your_market_data_app_key
XTS_MARKET_DATA_SECRET=your_market_data_secret_key
XTS_MARKET_DATA_SOURCE=WebAPI

# XTS Interactive (order placement)
XTS_INTERACTIVE_URL=https://developers.symphonyfintech.in
XTS_INTERACTIVE_KEY=your_interactive_app_key
XTS_INTERACTIVE_SECRET=your_interactive_secret_key
XTS_INTERACTIVE_SOURCE=WebAPI

# Database
DATABASE_URL=postgresql+asyncpg://trader:trader123@localhost:5432/trading_db

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# Risk defaults
DEFAULT_MAX_CAPITAL=500000
DEFAULT_MAX_DAILY_LOSS=25000
DEFAULT_MAX_OPEN_TRADES=10
```

---

## Local Development Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL and Redis (e.g. via Docker)
docker-compose up -d postgres redis

# 3. Run database migrations
alembic upgrade head

# 4. Start the API server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5. Start the React frontend (separate terminal)
cd frontend
npm install
npm start
```

- **API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Dashboard**: http://localhost:3000

---

## Docker Deployment

```bash
# Build and start all services
docker-compose up --build

# Or in detached mode
docker-compose up -d --build
```

Services started: `api`, `frontend`, `postgres`, `redis`

---

## XTS API Credentials

The platform uses the **Symphony Fintech XTS API**, which provides market data and order execution for Indian exchanges.

**Where to get credentials:**
1. Register at [Symphony Fintech Developer Portal](https://developers.symphonyfintech.in)
2. Create an application — you will receive two credential sets:
   - **Market Data** (`app_key` + `secret_key`): for subscribing to live market feeds
   - **Interactive** (`app_key` + `secret_key`): for placing, modifying, and cancelling orders

**Important notes:**
- The platform works in read-only/simulation mode without credentials — the API serves all endpoints but no live orders are placed.
- Use the Symphoney Fintech sandbox environment (`https://developers.symphonyfintech.in`) for testing.
- For production, replace with your broker's XTS endpoint URL.

---

## Strategy Descriptions

| Strategy | Description |
|----------|-------------|
| **Short Straddle** | Sell ATM CE + PE simultaneously. Profits from low volatility. SL/target at 50% of premium. |
| **Short Strangle** | Sell OTM CE + PE. Wider breakeven than straddle, lower premium. |
| **Iron Condor** | Sell OTM call spread + OTM put spread. Limited risk, profits in range-bound markets. |
| **Bull Call Spread** | Buy ITM call, sell OTM call. Bullish outlook with defined risk. |
| **Bear Put Spread** | Buy ITM put, sell OTM put. Bearish outlook with defined risk. |
| **Long Straddle** | Buy ATM CE + PE. Profits from large moves in either direction. |
| **Butterfly Spread** | Buy 1 ITM + 1 OTM call, sell 2 ATM calls. Profits at specific target price. |
| **Calendar Spread** | Sell near-expiry option, buy far-expiry at same strike. Profits from time decay. |
| **Covered Call** | Hold underlying + sell OTM call. Generates income on existing long position. |
| **Protective Put** | Hold underlying + buy OTM put. Insures against downside while keeping upside. |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/api/trades/open` | List all open trades |
| GET | `/api/trades/closed` | List closed trades (filterable by date, strategy) |
| GET | `/api/trades/{trade_id}` | Get trade details |
| POST | `/api/trades/squareoff/{trade_id}` | Square off a specific trade |
| POST | `/api/trades/squareoff-all` | Square off all open trades |
| GET | `/api/risk/config` | Get risk configuration |
| PUT | `/api/risk/config` | Update risk configuration |
| GET | `/api/risk/dashboard` | Risk metrics dashboard |
| POST | `/api/risk/kill-switch/activate` | Activate kill switch |
| POST | `/api/risk/kill-switch/deactivate` | Deactivate kill switch |
| GET | `/api/strategies` | List all strategies |
| PUT | `/api/strategies/{name}/toggle` | Enable/disable a strategy |
| GET | `/api/strategies/{name}/performance` | Per-strategy P&L metrics |
| GET | `/api/positions` | Live positions from broker |
| WS | `/ws/dashboard` | Real-time dashboard WebSocket feed |

Full interactive docs at **`/docs`** (Swagger UI) or **`/redoc`**.

---

## Risk Management Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_capital` | 500,000 | Maximum total capital allocated |
| `max_margin_utilization` | 0.80 | Max fraction of capital used as margin |
| `max_open_trades` | 10 | Maximum simultaneous open trades |
| `max_daily_loss` | 25,000 | Maximum realized loss per day (INR) |
| `max_per_strategy_trades` | 2 | Max open trades per strategy |
| `max_per_strategy_capital` | 100,000 | Max capital per strategy |
| `max_quantity_per_order` | 50 | Max lot quantity in a single order |
| `cooldown_seconds` | 60 | Minimum seconds between consecutive signals |
| `trading_enabled` | true | Master trading on/off switch |
| `allowed_symbols` | NIFTY, BANKNIFTY | Symbols the platform may trade |
| `allowed_segments` | NSEFO | Exchange segments allowed |

Update at runtime via `PUT /api/risk/config`.

---

## How to Add a New Strategy

1. **Create the strategy file** in `strategies/`:
   ```python
   # strategies/my_strategy.py
   from strategies.base_strategy import BaseStrategy
   from engine.signal import Signal
   from typing import Any, Dict, List

   class MyStrategy(BaseStrategy):
       def __init__(self, name="my_strategy", enabled=True):
           super().__init__(name=name, enabled=enabled)

       async def on_tick(self, data: Dict[str, Any]) -> List[Signal]:
           # implement signal logic
           return []

       async def on_order_update(self, data: Dict[str, Any]) -> None:
           pass
   ```

2. **Import and register** in `api/main.py` inside `_build_strategy_registry()`:
   ```python
   from strategies.my_strategy import MyStrategy
   # ...
   registry.register(MyStrategy())
   ```

3. **Verify** it appears in `GET /api/strategies`.

4. **Write tests** in `tests/test_strategies.py`.

---

## Architecture Overview

| Module | Description |
|--------|-------------|
| `core/event_bus.py` | Async pub/sub event bus connecting all components |
| `core/xts_client.py` | HTTP client for XTS Market Data and Interactive APIs |
| `core/market_data_socket.py` | SocketIO client for live market data feed |
| `core/order_socket.py` | SocketIO client for live order/trade updates |
| `engine/strategy_engine.py` | Distributes market events to all enabled strategies |
| `engine/instrument_manager.py` | ATM strike calculation and instrument lookup |
| `engine/signal.py` | Signal dataclass (action, symbol, qty, SL/target) |
| `strategies/` | 10 options strategy implementations |
| `risk/risk_manager.py` | Pre-trade risk validation engine |
| `risk/kill_switch.py` | Emergency halt with auto square-off |
| `execution/order_manager.py` | Order placement, modification, and cancellation |
| `execution/trade_manager.py` | Trade lifecycle tracking and P&L calculation |
| `execution/position_reconciler.py` | Periodic reconciliation against broker positions |
| `database/models.py` | SQLAlchemy ORM models |
| `api/main.py` | FastAPI app with lifespan startup/shutdown |
| `api/routes/` | REST endpoint handlers |
| `frontend/` | React dashboard with live WebSocket feed |

---

## Troubleshooting

**`XTS login failed` on startup**
> The platform still runs without XTS credentials — API endpoints work but no live orders are placed. Verify your `app_key` and `secret_key` in `.env`.

**`asyncpg.exceptions.ConnectionRefusedError`**
> PostgreSQL is not running. Start it with `docker-compose up -d postgres` or check your `DATABASE_URL`.

**Strategies not generating signals**
> 1. Check the strategy is enabled: `GET /api/strategies`
> 2. Verify trading hours (9:20 – 15:00 IST)
> 3. Confirm `trading_enabled: true` in `GET /api/risk/config`
> 4. Check daily loss limit not exceeded

**Kill switch accidentally activated**
> Call `POST /api/risk/kill-switch/deactivate` to resume trading.

**Frontend shows "Disconnected"**
> The WebSocket at `/ws/dashboard` requires the API to be running. Check `uvicorn` is up and CORS is configured.

**Alembic migration errors**
> Run `alembic history` to check current revision, then `alembic upgrade head` to apply all pending migrations.

---

## Running Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v --tb=short
```

Tests are self-contained and require no live credentials or running database.
