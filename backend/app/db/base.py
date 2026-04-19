"""SQLAlchemy 2.x declarative base.

Lives alone so both the application code (``app.db.models``) and the
Alembic env (``alembic/env.py``) can import it without dragging in
the rest of the package.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common base for every ORM model in the project."""
