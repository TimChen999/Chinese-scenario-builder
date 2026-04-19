"""Generation-job schemas.

See DESIGN.md Section 5 (`JobStatus` JSON shape).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobStatus(BaseModel):
    """Polled response for ``GET /jobs/{job_id}``."""

    id: str
    status: str  # pending | running | done | failed
    progress_stage: str | None = None
    scenario_id: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class HistoryItem(BaseModel):
    """One entry in the /history list."""

    attempt_id: int
    task_id: str
    scenario_id: str
    scenario_title: str
    task_prompt: str
    user_answer: str
    expected_answer: str
    is_correct: bool
    attempted_at: datetime


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None = None
