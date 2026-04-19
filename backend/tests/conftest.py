"""Shared pytest fixtures.

Every test gets a brand-new in-memory SQLite database wired into the
FastAPI app via ``app.dependency_overrides``. Production database is
never touched in tests because the override replaces the ``get_db``
dependency end-to-end.

The in-memory database is shared across all connections inside a
single test via :class:`StaticPool`; without that, each connection
would see a separate empty database (SQLite quirk).

See DESIGN.md Section 11 (Testing Strategy).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Force a deterministic, in-memory configuration BEFORE the app
# imports `get_settings`. We reset the lru_cache below as well, so
# any test that pre-imported the module still gets these values.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("SERPAPI_KEY", "test-serpapi-key")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
# Sandbox image storage so tests never write into ./data/images. One
# temp dir for the whole pytest session is fine -- file names are
# scenario_id-keyed so collisions across tests are vanishingly rare.
os.environ.setdefault(
    "IMAGE_STORAGE_DIR",
    tempfile.mkdtemp(prefix="scenarios_test_images_"),
)

from app.api import deps as api_deps  # noqa: E402
from app.core.config import get_settings  # noqa: E402  -- after env setup
from app.db import models  # noqa: F401, E402  -- ensure models registered with metadata
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services.job_runner import JobRunner  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _refresh_settings_cache() -> None:
    """Make sure pydantic-settings re-reads the test env vars."""
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """A fresh in-memory async engine per test; tables created up front.

    StaticPool keeps every connection bound to the same in-memory DB
    (otherwise SQLite gives each connection its own private DB and
    the schema we just created would be invisible).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """An ``AsyncSession`` bound to the per-test in-memory engine."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session


@pytest.fixture
def app(db_engine: AsyncEngine):
    """The FastAPI app with ``get_db`` rebound to the per-test engine.

    Also installs a per-test :class:`JobRunner` bound to that engine
    so background generation jobs use the in-memory database. The
    ``api_deps.get_db_session`` and ``api_deps.get_job_runner``
    dependencies are overridden; the underlying ``get_db`` is also
    overridden in case any module imports it directly.

    Cleans up dependency overrides on teardown so other tests are not
    polluted by leftover bindings.
    """
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    test_runner = JobRunner(session_maker=maker, settings=get_settings())

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.dependency_overrides[api_deps.get_db_session] = _override_get_db
    fastapi_app.dependency_overrides[api_deps.get_job_runner] = lambda: test_runner

    try:
        yield fastapi_app
    finally:
        fastapi_app.dependency_overrides.clear()
        # No await: the test runner's tasks are short-lived (mocked
        # orchestrators in tests) but cancel any stragglers anyway
        # so they do not leak across tests.
        for task in list(test_runner._tasks.values()):
            if not task.done():
                task.cancel()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """An ``httpx.AsyncClient`` wired to the test app via ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
