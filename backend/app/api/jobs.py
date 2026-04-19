"""``/jobs`` routes: poll a job, subscribe via Server-Sent Events.

See DESIGN.md Section 6:

* ``GET /jobs/{job_id}``         -- snapshot poll, returns JobStatus
* ``GET /jobs/{job_id}/stream``  -- SSE event stream

The SSE stream's event types are ``progress``, ``done``, ``failed``;
the ``data`` field is JSON. Frontend uses ``EventSource`` to consume.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_db_session, get_job_runner
from app.db.models import GenerationJob
from app.schemas.job import JobStatus
from app.services.job_runner import JobRunner

router = APIRouter(prefix="/jobs", tags=["jobs"])
log = logging.getLogger(__name__)


@router.get("/{job_id}", response_model=JobStatus)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JobStatus:
    """Return the current status of a generation job.

    Frontend uses this for poll-based fallback; the SSE stream is
    preferred when available.
    """
    job = await session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatus(
        id=job.id,
        status=job.status,
        progress_stage=job.progress_stage,
        scenario_id=job.scenario_id,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str,
    runner: JobRunner = Depends(get_job_runner),
) -> EventSourceResponse:
    """Server-Sent Events stream of a job's progress.

    Emits one ``progress`` event per orchestrator stage transition,
    then a terminal ``done`` event with ``{"scenario_id": ...}`` or
    a terminal ``failed`` event with ``{"error_message": ...}``.

    Note: this dependency does NOT verify the job exists in the DB
    -- ``runner.stream_events`` already handles the unknown-id case
    by closing the stream cleanly.
    """

    async def event_iter() -> AsyncIterator[dict]:
        async for event_type, data in runner.stream_events(job_id):
            yield {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}

    # send_timeout=None: SSE responses are inherently long-lived;
    # closing them on a tight write timeout would race with slow
    # downstream consumers (e.g. the browser tab in the background).
    return EventSourceResponse(event_iter())
