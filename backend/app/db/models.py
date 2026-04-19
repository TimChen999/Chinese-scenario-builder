"""SQLAlchemy ORM models -- four tables that own all persistent state.

Schema mirrors DESIGN.md Section 5 verbatim:

* :class:`Scenario`        -- one generated reading scene (image + text + setup)
* :class:`Task`            -- a comprehension question attached to a Scenario
* :class:`Attempt`         -- one user submission against a Task
* :class:`GenerationJob`   -- a background job that produces a Scenario

Cascades are configured so deleting a Scenario removes its Tasks +
Attempts; deleting a Task removes its Attempts; jobs persist
independently so we can investigate failures after the fact.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _new_uuid() -> str:
    """Return a 32-character hex string suitable for a primary key.

    Matches DESIGN.md Section 5 (32-char varchar IDs everywhere).
    """
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    """Return ``datetime.utcnow()`` -- factored out so tests can patch.

    Using ``datetime.utcnow`` deliberately (not ``now(tz=utc)``) so the
    SQLite ``DATETIME`` column stores naive UTC strings, matching the
    server-side ``CURRENT_TIMESTAMP`` defaults set in the migration.
    """
    return datetime.utcnow()


class Scenario(Base):
    """A generated reading scene built from a real-world photo.

    ``raw_content`` is the OCR output preserved byte-for-byte. The
    "authenticity invariant" (DESIGN.md Section 1, Section 5) is that
    no downstream code is ever allowed to alter this field after it
    leaves the OCR step.
    """

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    request_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    scene_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scene_setup: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    source_image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )

    tasks: Mapped[list[Task]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="Task.position_index",
    )


class Task(Base):
    """One comprehension question pointing at a Scenario.

    ``acceptable_answers`` is a JSON-encoded string list (kept as TEXT
    rather than a dedicated JSON column to stay portable across DBs).
    The application layer encodes/decodes via ``json``.
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    acceptable_answers: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    scenario: Mapped[Scenario] = relationship(back_populates="tasks")
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Attempt(Base):
    """A single submission against a Task.

    The first attempt per task counts toward the user's score; all
    subsequent attempts are still recorded but only displayed in
    /history (DESIGN.md Section 8 "Re-attempt" rule).
    """

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )

    task: Mapped[Task] = relationship(back_populates="attempts")


class GenerationJob(Base):
    """A background job that produces (or fails to produce) a Scenario.

    Status transitions: ``pending`` -> ``running`` -> ``done``/``failed``.
    The default ``"pending"`` is set at the Python level so newly
    constructed objects have the field populated even before flushing
    (the migration also sets a server-side default for direct SQL inserts).
    """

    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    request_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    progress_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
