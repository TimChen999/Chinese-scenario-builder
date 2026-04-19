"""Background generation-job runner + per-job SSE event queues.

Owns the bridge between the HTTP layer and the agent orchestrator
(DESIGN.md Section 7). Responsibilities:

* On ``start_job(prompt, hints)`` -- create a ``GenerationJob`` row,
  spawn an ``asyncio.create_task`` running the orchestrator, and
  return the job id.
* While the orchestrator runs, push every ``on_progress`` callback
  into a per-job ``asyncio.Queue`` so the SSE endpoint can fan
  events out to the browser.
* On orchestrator success -- persist the resulting ``ScenarioDraft``
  (Scenario row + Tasks + image file), mark the job ``done``, and
  emit a terminal ``done`` event.
* On orchestrator failure -- mark the job ``failed`` with the
  ``GenerationFailed.detail`` and emit a terminal ``failed`` event.

We deliberately use ``asyncio.create_task`` (NOT FastAPI's
``BackgroundTasks``) so the job survives the originating request
disconnecting -- a long generation should not be held hostage by
flaky browser connections.

Single-process, single-machine v1: all state lives in the running
Python process. Restarting the backend abandons in-flight jobs but
preserves all completed Scenarios + Tasks because those are
persisted to SQLite as soon as they're built.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.orchestrator import GenerationFailed, run_generation
from app.agent.types import ScenarioDraft
from app.core.config import Settings
from app.db.models import GenerationJob, Scenario, Task
from app.services.image_store import save_image

log = logging.getLogger(__name__)


class JobRunner:
    """Process-wide owner of in-flight generation jobs.

    Construct one per app instance; tests construct a fresh runner
    bound to their in-memory engine.

    Attributes
    ----------
    _session_maker
        Used to build a brand-new ``AsyncSession`` inside the
        background task. The request-scoped session is closed by the
        time the orchestrator finishes, so we cannot reuse it.
    _settings
        Passed through to the agent layer for API keys etc.
    _queues
        ``job_id`` -> per-job event queue. Populated on start_job;
        cleared on stream_events finally.
    _tasks
        ``job_id`` -> the ``asyncio.Task`` running the orchestrator.
        Held so we can cancel them on shutdown if needed.
    """

    def __init__(
        self,
        *,
        session_maker: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_maker = session_maker
        self._settings = settings
        self._queues: dict[str, asyncio.Queue[tuple[str, dict[str, Any]]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # ─── Public API ────────────────────────────────────────────

    async def start_job(
        self,
        request_prompt: str,
        *,
        scene_hint: str | None = None,
        region: str | None = None,
        format_hint: str | None = None,
    ) -> str:
        """Persist a pending GenerationJob row and spawn the orchestrator.

        Returns the job id immediately; the orchestrator continues
        in the background and the caller polls / streams via the
        other methods.
        """
        async with self._session_maker() as session:
            job = GenerationJob(request_prompt=request_prompt, status="pending")
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id: str = job.id

        # Queue must exist before any consumer connects, so we
        # populate it BEFORE create_task to avoid a race.
        self._queues[job_id] = asyncio.Queue()
        self._tasks[job_id] = asyncio.create_task(
            self._run(
                job_id=job_id,
                request_prompt=request_prompt,
                scene_hint=scene_hint,
                region=region,
                format_hint=format_hint,
            )
        )
        return job_id

    async def stream_events(
        self, job_id: str
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield (event_type, data) tuples for a job until terminal.

        If the queue has already been cleaned up (job completed long
        ago) we synthesise a single terminal event from the
        persisted ``GenerationJob`` row.
        """
        queue = self._queues.get(job_id)
        if queue is None:
            async with self._session_maker() as session:
                job = await session.get(GenerationJob, job_id)
                if job is None:
                    return
                if job.status == "done":
                    yield ("done", {"scenario_id": job.scenario_id})
                elif job.status == "failed":
                    yield ("failed", {"error_message": job.error_message or "unknown"})
                # else still pending/running -- caller should retry
            return

        try:
            while True:
                event_type, data = await queue.get()
                yield (event_type, data)
                if event_type in ("done", "failed"):
                    break
        finally:
            # Drop the queue so the second consumer falls through to
            # the DB-backed path. Memory bound: one queue per
            # in-flight job, freed on first complete consume.
            self._queues.pop(job_id, None)

    # ─── Internal background-task body ────────────────────────

    async def _run(
        self,
        *,
        job_id: str,
        request_prompt: str,
        scene_hint: str | None,
        region: str | None,
        format_hint: str | None,
    ) -> None:
        """Orchestrator wrapper executed inside ``asyncio.create_task``.

        Handles the database transitions (running / done / failed)
        and translates ``on_progress`` callbacks into queued SSE
        events. All exceptions are caught -- an uncaught exception
        here would silently kill the task and leave the job stuck
        in ``running`` forever.
        """
        queue = self._queues[job_id]

        async def on_progress(stage: str, detail: dict[str, Any]) -> None:
            await queue.put(("progress", {"stage": stage, **detail}))
            # Best-effort progress_stage update on the row so
            # /jobs/{id} polling reflects the stage too.
            try:
                async with self._session_maker() as session:
                    job = await session.get(GenerationJob, job_id)
                    if job is not None:
                        job.status = "running"
                        job.progress_stage = stage
                        await session.commit()
            except Exception:  # noqa: BLE001 -- progress update is non-critical
                log.exception("failed to update progress_stage for job=%s", job_id)

        try:
            draft: ScenarioDraft = await run_generation(
                request_prompt,
                scene_hint=scene_hint,
                region=region,
                format_hint=format_hint,
                on_progress=on_progress,
                settings=self._settings,
            )
        except GenerationFailed as exc:
            await self._mark_failed(job_id, f"{exc.stage}: {exc.detail}", queue)
            return
        except Exception as exc:  # noqa: BLE001 -- defensive last line
            log.exception("orchestrator crashed for job=%s", job_id)
            await self._mark_failed(job_id, f"unexpected: {exc}", queue)
            return

        try:
            scenario_id = await self._persist_success(
                job_id, request_prompt, draft
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("failed to persist success for job=%s", job_id)
            await self._mark_failed(job_id, f"persist: {exc}", queue)
            return

        await queue.put(("done", {"scenario_id": scenario_id}))

    async def _persist_success(
        self,
        job_id: str,
        request_prompt: str,
        draft: ScenarioDraft,
    ) -> str:
        """Write Scenario + Tasks + image and flip the job to done.

        Returns the new scenario id so the caller can include it in
        the terminal SSE event.
        """
        async with self._session_maker() as session:
            scenario = Scenario(
                request_prompt=request_prompt,
                scene_type=draft.scene_type,
                scene_setup=draft.scene_setup,
                # Authenticity invariant -- raw_content is verbatim OCR.
                raw_content=draft.raw_content,
                source_url=draft.source_image.original.url,
                search_query=draft.source_image.original.title,
                tasks=[
                    Task(
                        position_index=i,
                        prompt=t.prompt,
                        answer_type=t.answer_type,
                        expected_answer=t.expected_answer,
                        acceptable_answers=json.dumps(
                            t.acceptable_answers, ensure_ascii=False
                        ),
                        explanation=t.explanation,
                    )
                    for i, t in enumerate(draft.tasks)
                ],
            )
            session.add(scenario)
            await session.flush()  # populate scenario.id
            scenario_id: str = scenario.id

            # Save the image to disk keyed by scenario_id, then
            # record the path on the row.
            try:
                image_path = save_image(
                    scenario_id, draft.source_image, settings=self._settings
                )
                scenario.source_image_path = str(image_path)
            except Exception:  # noqa: BLE001 -- image is nice-to-have
                log.exception("failed to save image for scenario=%s", scenario_id)

            job = await session.get(GenerationJob, job_id)
            if job is not None:
                job.status = "done"
                job.scenario_id = scenario_id
                job.completed_at = datetime.utcnow()
                job.progress_stage = "done"

            await session.commit()
            return scenario_id

    async def _mark_failed(
        self,
        job_id: str,
        error_message: str,
        queue: asyncio.Queue[tuple[str, dict[str, Any]]],
    ) -> None:
        """Record failure on the row and emit the terminal SSE event."""
        try:
            async with self._session_maker() as session:
                job = await session.get(GenerationJob, job_id)
                if job is not None:
                    job.status = "failed"
                    job.error_message = error_message
                    job.completed_at = datetime.utcnow()
                    await session.commit()
        except Exception:  # noqa: BLE001
            log.exception("failed to mark job=%s as failed", job_id)
        await queue.put(("failed", {"error_message": error_message}))

    # ─── Test helpers ─────────────────────────────────────────

    async def shutdown(self) -> None:
        """Cancel all in-flight tasks. Used in test teardown."""
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        for task in list(self._tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks.clear()
        self._queues.clear()


# ─── Listing helpers used by the API layer ────────────────────────


async def list_recent_jobs(
    session: AsyncSession, *, limit: int = 20
) -> list[GenerationJob]:
    """Return the most recent generation jobs in descending creation order.

    Currently unused by the public API but handy for debugging via a
    REPL ("why did my last 5 generations fail?"). Kept here so it
    lives next to the persistence side of jobs.
    """
    stmt = (
        select(GenerationJob)
        .order_by(GenerationJob.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
