"""Database session and engine management."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from database.models import Base

logger = structlog.get_logger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def init_db(database_url: str, echo: bool = False) -> AsyncEngine:
    """Initialize the async database engine and session factory."""
    global _engine, _session_factory

    _engine = create_async_engine(database_url, echo=echo, future=True)
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized", url=database_url)
    return _engine


async def create_tables():
    """Create all tables defined in models."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")


async def drop_tables():
    """Drop all tables (use with caution)."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Database tables dropped")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db():
    """Dispose the engine and close all connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")
