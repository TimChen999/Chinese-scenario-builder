"""Alembic migration environment.

Reads the database URL from `app.core.config.get_settings()` so we have
a single source of truth for connection strings. See DESIGN.md Section 4.

Alembic itself runs synchronously, so we strip the `+aiosqlite` async
driver prefix from the URL when running migrations -- the schema we
emit is identical either way; only the driver differs.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings

# Import models so Base.metadata is populated before autogenerate runs.
from app.db import models  # noqa: F401  -- side-effect import for metadata
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    """Return the configured DB URL with the async driver stripped.

    Alembic uses a synchronous engine; the application uses
    aiosqlite. Both speak the same SQLite file format so we just
    swap the driver.

    Side effect: for SQLite file URLs, ensure the parent directory
    exists. SQLite refuses to create a database file inside a
    missing directory, so this saves the user from having to
    ``mkdir data`` on first run.
    """
    from pathlib import Path

    url = get_settings().DATABASE_URL.replace("sqlite+aiosqlite", "sqlite", 1)

    # For SQLite file URLs (sqlite:///./data/scenarios.db), make sure
    # the parent directory exists; SQLite refuses to create a DB file
    # inside a missing directory. ":memory:" has no parent.
    if url.startswith("sqlite:///"):
        path_part = url[len("sqlite:///") :]
        if path_part and path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)

    return url


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the database.

    Useful for code review and CI; not used in normal local dev.
    """
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
