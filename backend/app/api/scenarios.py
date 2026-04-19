"""``/scenarios`` routes: generate, list, retrieve.

See DESIGN.md Section 6 for the full contract:

* ``POST /scenarios/generate`` -- start a job, return ``{"job_id": ...}``
* ``GET  /scenarios``          -- cursor-paginated library list
* ``GET  /scenarios/{id}``     -- full scenario for the reader page

Image serving lives in ``api/images.py``; answer evaluation lives in
``api/tasks.py``; the SSE stream lives in ``api/jobs.py``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session, get_job_runner
from app.db.models import Scenario, Task
from app.schemas.scenario import (
    GenerateRequest,
    GenerateResponse,
    ScenarioListResponse,
    ScenarioOut,
    ScenarioSummary,
)
from app.schemas.task import TaskOut
from app.services.job_runner import JobRunner

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _image_url_for(request: Request, scenario: Scenario) -> str | None:
    """Return the public URL the frontend should fetch the image from.

    Returns None when no image was saved (e.g. an older scenario or a
    job that completed but failed at image-save time).
    """
    if not scenario.source_image_path:
        return None
    return str(request.url_for("get_scenario_image", scenario_id=scenario.id))


def _task_to_out(task: Task) -> TaskOut:
    """Project a Task ORM row to its public-facing schema."""
    return TaskOut(
        id=task.id,
        position_index=task.position_index,
        prompt=task.prompt,
        answer_type=task.answer_type,
        explanation=task.explanation,
    )


def _scenario_to_summary(scenario: Scenario, *, request: Request, task_count: int) -> ScenarioSummary:
    return ScenarioSummary(
        id=scenario.id,
        request_prompt=scenario.request_prompt,
        scene_type=scenario.scene_type,
        scene_setup=scenario.scene_setup,
        source_image_url=_image_url_for(request, scenario),
        source_url=scenario.source_url,
        created_at=scenario.created_at,
        task_count=task_count,
    )


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_scenario(
    body: GenerateRequest,
    runner: JobRunner = Depends(get_job_runner),
) -> GenerateResponse:
    """Kick off a generation job; returns the job id immediately.

    202 Accepted because the work has been *accepted* but not
    *completed*. Clients then poll ``GET /jobs/{id}`` or subscribe
    to the SSE stream.
    """
    job_id = await runner.start_job(
        body.prompt,
        scene_hint=body.scene_hint,
        region=body.region,
        format_hint=body.format_hint,
    )
    return GenerateResponse(job_id=job_id)


@router.get("", response_model=ScenarioListResponse)
async def list_scenarios(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
    scene_type: str | None = Query(default=None),
) -> ScenarioListResponse:
    """Cursor-paginated library list, newest first.

    The cursor is the id of the last item from the previous page;
    we look it up to find its ``created_at`` and slice strictly
    older rows. Robust against new scenarios appearing mid-scroll.
    """
    stmt = select(Scenario).order_by(Scenario.created_at.desc(), Scenario.id.desc())
    if scene_type:
        stmt = stmt.where(Scenario.scene_type == scene_type)

    if cursor:
        cursor_row = await session.get(Scenario, cursor)
        if cursor_row is not None:
            stmt = stmt.where(
                (Scenario.created_at < cursor_row.created_at)
                | (
                    (Scenario.created_at == cursor_row.created_at)
                    & (Scenario.id < cursor)
                )
            )

    # Over-fetch by one to detect a next page without a separate
    # COUNT. The cursor is the id of the LAST row on the page (not
    # the peeked-at row), so the next call walks strictly past it.
    stmt = stmt.limit(limit + 1)
    items = list((await session.execute(stmt)).scalars().all())
    has_more = len(items) > limit
    page = items[:limit]
    next_cursor = page[-1].id if has_more and page else None

    # Cheap follow-up query: task counts per scenario in the page.
    if page:
        count_stmt = (
            select(Task.scenario_id, func.count(Task.id))
            .where(Task.scenario_id.in_([s.id for s in page]))
            .group_by(Task.scenario_id)
        )
        rows = (await session.execute(count_stmt)).all()
        counts: dict[str, int] = {sid: cnt for sid, cnt in rows}
    else:
        counts = {}

    return ScenarioListResponse(
        items=[
            _scenario_to_summary(s, request=request, task_count=counts.get(s.id, 0))
            for s in page
        ],
        next_cursor=next_cursor,
    )


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(
    scenario_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ScenarioOut:
    """Return one scenario including its full task list.

    404 if the id does not exist. The tasks are loaded eagerly via
    ``selectinload`` to avoid N+1 lazy loads on serialisation.
    """
    stmt = (
        select(Scenario)
        .options(selectinload(Scenario.tasks))
        .where(Scenario.id == scenario_id)
    )
    scenario = (await session.execute(stmt)).scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    return ScenarioOut(
        id=scenario.id,
        request_prompt=scenario.request_prompt,
        scene_type=scenario.scene_type,
        scene_setup=scenario.scene_setup,
        raw_content=scenario.raw_content,
        source_image_url=_image_url_for(request, scenario),
        source_url=scenario.source_url,
        created_at=scenario.created_at,
        tasks=[_task_to_out(t) for t in scenario.tasks],
    )


# Helper exported for tasks.py + history.py.

def parse_acceptable_answers(value: str | None) -> list[str]:
    """Decode the JSON-encoded ``acceptable_answers`` column.

    Returns an empty list for None / invalid JSON so callers do not
    need to re-implement the defensive try/except.
    """
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]
