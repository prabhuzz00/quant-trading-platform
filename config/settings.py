from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

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


settings = Settings()
