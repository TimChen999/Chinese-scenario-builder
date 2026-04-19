"""Scenario-related HTTP schemas.

See DESIGN.md Section 5 (`ScenarioOut` JSON shape) and Section 6.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.task import TaskOut


class GenerateRequest(BaseModel):
    """POST /scenarios/generate body."""

    prompt: str = Field(..., min_length=1, max_length=500)
    scene_hint: str | None = Field(default=None, max_length=32)
    region: str | None = Field(default=None, max_length=64)
    format_hint: str | None = Field(default=None, max_length=32)


class GenerateResponse(BaseModel):
    """202 response for /scenarios/generate."""

    job_id: str


class ScenarioSummary(BaseModel):
    """Lightweight scenario card for the library grid.

    Excludes ``raw_content`` and the full task list -- those would
    blow up the payload for a 100-card grid and the UI does not
    need them at this view.
    """

    id: str
    request_prompt: str
    scene_type: str
    scene_setup: str
    source_image_url: str | None = None
    source_url: str | None = None
    created_at: datetime
    task_count: int


class ScenarioOut(BaseModel):
    """Full scenario for the reader page."""

    id: str
    request_prompt: str
    scene_type: str
    scene_setup: str
    raw_content: str
    source_image_url: str | None = None
    source_url: str | None = None
    created_at: datetime
    tasks: list[TaskOut]


class ScenarioListResponse(BaseModel):
    """Cursor-paginated list response."""

    items: list[ScenarioSummary]
    next_cursor: str | None = None
