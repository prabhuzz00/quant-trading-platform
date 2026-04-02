from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import secrets
from pathlib import Path

# Resolve .env relative to this file so it always loads correctly regardless
# of the working directory (e.g. uvicorn --reload spawns a subprocess whose
# CWD may differ from the project root).
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding='utf-8', extra='ignore')

    # XTS Market Data
    xts_market_data_url: str = "https://developers.symphonyfintech.in"
    xts_market_data_key: str = ""
    xts_market_data_secret: str = ""
    xts_market_data_source: str = "WebAPI"

    # XTS Interactive
    xts_interactive_url: str = "https://developers.symphonyfintech.in"
    xts_interactive_key: str = ""
    xts_interactive_secret: str = ""
    xts_interactive_source: str = "WebAPI"
    xts_interactive_client_id: str = ""  # Client trading ID for dealer/CTCL mode (e.g. "WD1768")

    # Set to False if the broker endpoint uses a self-signed / private CA certificate
    xts_verify_ssl: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://trader:trader123@localhost:5432/trading_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # App
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = Field(default_factory=lambda: secrets.token_hex(32))

    # Risk defaults
    default_max_capital: float = 500000
    default_max_daily_loss: float = 25000
    default_max_open_trades: int = 10

    # Historical candle warm-up
    candle_lookback_default: int = 100
    candle_cache_ttl_seconds: int = 3600
    candle_max_store_size: int = 500

    # AI Regime Engine
    regime_enabled: bool = False          # auto-toggle strategies based on regime
    regime_interval_minutes: int = 15     # how often the background loop fires
    regime_score_threshold: int = 80      # min score (0-100) to enable a strategy
    regime_instrument_id: int = 26000     # candle instrument for regime detection (NIFTY 50)
    regime_timeframe: int = 5             # candle timeframe in minutes

    # OHLCV data fetch defaults (Nifty 50)
    ohlcv_default_segment: str = "NSECM"
    ohlcv_default_instrument_id: int = 26000   # NIFTY 50 on NSE Cash
    ohlcv_default_symbol: str = "NIFTY 50"
    ohlcv_default_timeframe: int = 1           # 1-minute candles
    ohlcv_default_lookback_days: int = 5


settings = Settings()
