"""Common FastAPI dependencies shared by every router.

* :func:`get_db_session`   -- yields a request-scoped ``AsyncSession``.
* :func:`get_settings_dep` -- typed accessor over :mod:`app.core.config`.
* :func:`get_job_runner`   -- the in-process :class:`JobRunner` singleton.

Tests override ``get_job_runner`` in particular so each test gets a
runner bound to its in-memory engine + temp image directory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.job_runner import JobRunner

# Re-export the session dependency so route modules import it from
# one place. Also lets a test override `app.api.deps.get_db_session`
# without touching `app.db.session.get_db` directly.


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dep: yields a fresh ``AsyncSession`` per request."""
    async for session in get_db():
        yield session


def get_settings_dep() -> Settings:
    """FastAPI dep: returns the cached :class:`Settings`."""
    return get_settings()


# ─── Job runner singleton (lazy, dependency-overridable) ──────────

_job_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    """Return the process-wide :class:`JobRunner`, building it on demand.

    Tests override this dep with a runner bound to their in-memory
    engine; production calls fall through to the lazy singleton.
    """
    global _job_runner
    if _job_runner is None:
        from app.db.session import get_session_maker

        _job_runner = JobRunner(
            session_maker=get_session_maker(), settings=get_settings()
        )
    return _job_runner


def reset_job_runner_for_tests() -> None:
    """Test-only: clear the cached singleton."""
    global _job_runner
    _job_runner = None
