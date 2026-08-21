"""Database engine and session factory.

One engine per process, created lazily so importing a module never opens a
connection -- the api, poller and scheduler all import :mod:`shared.db` and only
some of them talk to Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from shared.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            # Normalised, because Render hands over a driverless postgresql://
            settings.async_database_url,
            pool_pre_ping=True,  # Render recycles idle connections
            pool_size=5,
            max_overflow=5,
            echo=False,
        )
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(engine(), expire_on_commit=False)
    return _factory


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    """A transactional session. Commits on success, rolls back on any exception."""
    async with session_factory()() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def dispose() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
