"""Async engine + session-maker factories.

Both factories are lazy so importing this module is cheap; the engine
is built on first call. Tests override the FastAPI ``get_db``
dependency with a session bound to an in-memory engine, so the
production engine is never touched in tests.

See DESIGN.md Section 4 (Folder Structure) and Section 12.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on demand.

    Idempotent. Safe to call from request handlers and from
    application startup hooks alike.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        # echo=False keeps logs quiet by default; flip via SQLAlchemy
        # env var SQLALCHEMY_ECHO=true if you need to see queries.
        _engine = create_async_engine(settings.DATABASE_URL, future=True, echo=False)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session maker bound to :func:`get_engine`."""
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_maker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a fresh ``AsyncSession`` per request.

    The session is committed only by the route handler; this dependency
    just owns connection acquisition + cleanup so handlers never leak
    sessions on error paths.
    """
    maker = get_session_maker()
    async with maker() as session:
        yield session


def reset_engine_for_tests() -> None:
    """Clear the cached engine + session maker so tests can swap configs.

    Test-only helper. Calling this in production would orphan any
    in-flight connections.
    """
    global _engine, _session_maker
    _engine = None
    _session_maker = None
