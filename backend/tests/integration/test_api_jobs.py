"""Integration tests for ``/jobs`` routes (polling + SSE).

The orchestrator is patched per-test so jobs complete (or fail)
deterministically in milliseconds.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.agent.orchestrator import GenerationFailed
from app.agent.types import DownloadedImage, ImageResult, ScenarioDraft, TaskDraft


def _patch_orchestrator_success(
    monkeypatch: pytest.MonkeyPatch, *, progress_stages: list[str] | None = None
) -> None:
    """Replace run_generation with a fake that always succeeds."""
    fake_image = DownloadedImage(
        bytes_=b"fake",
        mime="image/jpeg",
        original=ImageResult(url="https://example.com/x.jpg", title="x"),
    )

    stages = progress_stages or [
        "queries_generated",
        "images_searched",
        "images_filtered",
    ]

    async def fake(prompt, *, on_progress=None, **kwargs):
        if on_progress is not None:
            for s in stages:
                await on_progress(s, {})
        return ScenarioDraft(
            scene_type="menu",
            scene_setup="你刚走进早餐店。",
            raw_content="豆浆 3元",
            tasks=[
                TaskDraft(
                    prompt="q", answer_type="exact", expected_answer="豆浆",
                    acceptable_answers=["豆浆"], explanation=None,
                )
            ],
            source_image=fake_image,
        )

    monkeypatch.setattr("app.services.job_runner.run_generation", fake)


def _patch_orchestrator_failure(
    monkeypatch: pytest.MonkeyPatch, *, stage: str = "filter", detail: str = "no keepers"
) -> None:
    """Replace run_generation with a fake that raises GenerationFailed."""

    async def fake(prompt, *, on_progress=None, **kwargs):
        if on_progress is not None:
            await on_progress("queries_generated", {})
        raise GenerationFailed(stage, detail)

    monkeypatch.setattr("app.services.job_runner.run_generation", fake)


# ─── GET /jobs/{id} polling ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_polling(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Start a job, poll /jobs/{id} until done, assert scenario_id appears."""
    _patch_orchestrator_success(monkeypatch)

    start_resp = await client.post("/scenarios/generate", json={"prompt": "x"})
    assert start_resp.status_code == 202
    job_id = start_resp.json()["job_id"]

    final = None
    for _ in range(40):
        resp = await client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        final = resp.json()
        if final["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)

    assert final is not None
    assert final["status"] == "done", final
    assert final["scenario_id"], "scenario_id should be populated on done"


# ─── GET /jobs/{id}/stream (SSE) ──────────────────────────────────


@pytest.mark.asyncio
async def test_sse_stream(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSE stream emits progress events and a terminal ``done`` event in order."""
    _patch_orchestrator_success(
        monkeypatch,
        progress_stages=["queries_generated", "images_searched", "ocr_in_progress"],
    )

    start_resp = await client.post("/scenarios/generate", json={"prompt": "x"})
    job_id = start_resp.json()["job_id"]

    async with client.stream("GET", f"/jobs/{job_id}/stream") as response:
        assert response.status_code == 200
        body = await response.aread()

    text = body.decode("utf-8")
    # Events appear in order in the raw SSE text.
    pos_q = text.find("queries_generated")
    pos_s = text.find("images_searched")
    pos_o = text.find("ocr_in_progress")
    pos_done = text.find("event: done")
    assert pos_q != -1, text
    assert pos_s != -1, text
    assert pos_o != -1, text
    assert pos_done != -1, text
    assert pos_q < pos_s < pos_o < pos_done


@pytest.mark.asyncio
async def test_sse_stream_failure(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the orchestrator raises, SSE emits a terminal ``failed`` event."""
    _patch_orchestrator_failure(monkeypatch, stage="filter", detail="no usable images")

    start_resp = await client.post("/scenarios/generate", json={"prompt": "x"})
    job_id = start_resp.json()["job_id"]

    async with client.stream("GET", f"/jobs/{job_id}/stream") as response:
        body = await response.aread()

    text = body.decode("utf-8")
    assert "event: failed" in text
    assert "filter" in text
    assert "no usable images" in text
