"""SQLAlchemy ORM models for the trading platform."""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), unique=True, nullable=False, index=True)
    signal_id = Column(String(32), nullable=True)
    strategy_name = Column(String(128), nullable=False)
    symbol = Column(String(64), nullable=False)
    exchange_segment = Column(String(32), nullable=False)
    exchange_instrument_id = Column(BigInteger, nullable=False)
    action = Column(String(8), nullable=False)
    order_mode = Column(String(16), nullable=False)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Float, nullable=False, default=0.0)
    filled_qty = Column(Integer, nullable=False, default=0)
    avg_price = Column(Float, nullable=False, default=0.0)
    stoploss_points = Column(Float, nullable=False, default=0.0)
    target_points = Column(Float, nullable=False, default=0.0)
    pnl = Column(Float, nullable=False, default=0.0)
    status = Column(String(16), nullable=False, default="PENDING")
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(64), nullable=False)
    actor = Column(String(64), nullable=False, default="system")
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False)
    strategy_name = Column(String(128), nullable=True)
    symbol = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    daily_loss = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
