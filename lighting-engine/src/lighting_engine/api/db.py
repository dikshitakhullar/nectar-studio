"""SQLAlchemy 2.0 async engine + session factory.

Default URL is ``sqlite+aiosqlite:///data/state.db`` (resolved relative to the
lighting-engine root). Tests override via the ``LIGHTING_ENGINE_DB_URL`` env
var — typically ``sqlite+aiosqlite:///:memory:`` for ephemeral in-memory state.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_ENGINE: AsyncEngine | None = None
_SESSION_FACTORY: async_sessionmaker[AsyncSession] | None = None


def _default_db_url() -> str:
    """Build the default ``data/state.db`` URL anchored at the lighting-engine
    project root (the directory containing ``pyproject.toml``)."""
    here = Path(__file__).resolve()
    # src/lighting_engine/api/db.py → project root is parents[3]
    root = here.parents[3]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{data_dir / 'state.db'}"


def get_database_url() -> str:
    env = os.environ.get("LIGHTING_ENGINE_DB_URL")
    if env:
        return env
    return _default_db_url()


def get_engine() -> AsyncEngine:
    """Lazy-initialise the global async engine."""
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is None:
        url = get_database_url()
        # SQLite-specific: ``check_same_thread=False`` is irrelevant under
        # aiosqlite (driver is single-threaded async). No special connect_args
        # needed.
        _ENGINE = create_async_engine(url, future=True, echo=False)
        _SESSION_FACTORY = async_sessionmaker(
            bind=_ENGINE, expire_on_commit=False, class_=AsyncSession,
        )
    return _ENGINE


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global session factory, initialising the engine if needed."""
    if _SESSION_FACTORY is None:
        get_engine()
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


async def init_db() -> None:
    """Create all tables if they don't already exist.

    Called on FastAPI startup. Importing ``models`` here ensures the ORM
    classes are registered against ``Base.metadata`` before ``create_all``.
    """
    from lighting_engine.api.models import Base  # local import: avoid cycle

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    """Close the engine (FastAPI shutdown hook + test teardown)."""
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        await _ENGINE.dispose()
        _ENGINE = None
        _SESSION_FACTORY = None


def reset_engine_for_tests() -> None:
    """Drop the cached engine so the next call re-reads
    ``LIGHTING_ENGINE_DB_URL``. Used by the test fixtures.

    Note: callers are responsible for awaiting ``dispose_db()`` first if the
    engine was actively used.
    """
    global _ENGINE, _SESSION_FACTORY
    _ENGINE = None
    _SESSION_FACTORY = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an async session bound to the global engine."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
