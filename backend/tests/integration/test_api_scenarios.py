"""Integration tests for ``/scenarios`` routes.

The orchestrator is replaced with a fast fake (``mock_orchestrator``)
so each test's POST /scenarios/generate finishes in milliseconds.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import DownloadedImage, ImageResult, ScenarioDraft, TaskDraft
from app.db.models import Scenario, Task


@pytest.fixture
def mock_orchestrator(monkeypatch: pytest.MonkeyPatch):
    """Patch ``run_generation`` (as seen from job_runner) with a fast fake."""
    fake_image = DownloadedImage(
        bytes_=b"fake-jpeg-bytes",
        mime="image/jpeg",
        original=ImageResult(url="https://example.com/x.jpg", title="x"),
    )

    async def fake(
        prompt,
        *,
        on_progress=None,
        scene_hint=None,
        region=None,
        format_hint=None,
        settings=None,
    ):
        if on_progress is not None:
            await on_progress("queries_generated", {"queries": ["q"]})
        return ScenarioDraft(
            scene_type="menu",
            scene_setup="你刚走进早餐店。",
            raw_content="豆浆 3元\n油条 2元",
            tasks=[
                TaskDraft(
                    prompt="cheapest?",
                    answer_type="exact",
                    expected_answer="油条",
                    acceptable_answers=["油条", "youtiao"],
                    explanation="2元",
                )
            ],
            source_image=fake_image,
        )

    monkeypatch.setattr("app.services.job_runner.run_generation", fake)


async def _seed_scenarios(session: AsyncSession, n: int) -> list[Scenario]:
    """Insert ``n`` scenarios with one task each; return them in insert order."""
    rows: list[Scenario] = []
    for i in range(n):
        s = Scenario(
            request_prompt=f"prompt {i}",
            scene_type="menu" if i % 2 == 0 else "sign",
            scene_setup=f"你刚走进{i}号店。",
            raw_content=f"内容 {i}",
            tasks=[
                Task(
                    position_index=0,
                    prompt=f"task {i}",
                    answer_type="exact",
                    expected_answer="a",
                    acceptable_answers='["a"]',
                )
            ],
        )
        session.add(s)
        rows.append(s)
    await session.commit()
    return rows


# ─── POST /scenarios/generate ─────────────────────────────────────


@pytest.mark.asyncio
async def test_post_generate_returns_job_id(
    client: AsyncClient, mock_orchestrator
) -> None:
    """A successful POST returns 202 + a non-empty ``job_id``."""
    response = await client.post(
        "/scenarios/generate", json={"prompt": "ordering breakfast"}
    )
    assert response.status_code == 202
    body = response.json()
    assert "job_id" in body and isinstance(body["job_id"], str) and body["job_id"]


@pytest.mark.asyncio
async def test_post_generate_validation(client: AsyncClient) -> None:
    """An empty prompt fails Pydantic validation -> 422."""
    response = await client.post("/scenarios/generate", json={"prompt": ""})
    assert response.status_code == 422


# ─── GET /scenarios ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_scenarios_empty(client: AsyncClient) -> None:
    """An empty DB returns an empty list, not a 404."""
    response = await client.get("/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_scenarios_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """All seeded scenarios are returned with summary metadata."""
    await _seed_scenarios(db_session, 3)
    response = await client.get("/scenarios")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    # Each item carries the lightweight summary fields.
    for item in items:
        assert "id" in item
        assert "request_prompt" in item
        assert "scene_type" in item
        assert "scene_setup" in item
        assert item["task_count"] == 1


# ─── GET /scenarios/{id} ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_scenario_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Full scenario including tasks is returned by id."""
    scenario = Scenario(
        request_prompt="ordering breakfast",
        scene_type="menu",
        scene_setup="你刚走进早餐店。",
        raw_content="豆浆 3元\n油条 2元",
        tasks=[
            Task(
                position_index=0,
                prompt="cheapest?",
                answer_type="exact",
                expected_answer="油条",
                acceptable_answers='["油条"]',
                explanation="2元",
            ),
            Task(
                position_index=1,
                prompt="how much for both?",
                answer_type="numeric",
                expected_answer="5",
                acceptable_answers='["5"]',
            ),
        ],
    )
    db_session.add(scenario)
    await db_session.commit()
    sid = scenario.id

    response = await client.get(f"/scenarios/{sid}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == sid
    assert body["raw_content"] == "豆浆 3元\n油条 2元"
    assert len(body["tasks"]) == 2
    assert body["tasks"][0]["prompt"] == "cheapest?"
    # expected_answer / acceptable_answers must NOT leak in the public schema.
    assert "expected_answer" not in body["tasks"][0]
    assert "acceptable_answers" not in body["tasks"][0]


@pytest.mark.asyncio
async def test_get_scenario_404(client: AsyncClient) -> None:
    """Unknown id returns 404."""
    response = await client.get("/scenarios/nonsuchid")
    assert response.status_code == 404


# Unused imports below silence noise from above.
_ = asyncio
