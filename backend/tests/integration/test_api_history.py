"""Integration tests for ``GET /history``.

Empty / paginated / filtered cases, plus the cursor round-trip.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attempt, Scenario, Task


async def _seed_attempts(
    session: AsyncSession,
    *,
    n: int,
    correct_pattern: list[bool] | None = None,
) -> list[Attempt]:
    """Seed a single scenario + task and ``n`` attempts on it.

    ``attempted_at`` is staggered by 1 ms per attempt so the cursor
    pagination ordering is deterministic across SQLite's coarse
    timestamp resolution.
    """
    scenario = Scenario(
        request_prompt="test",
        scene_type="menu",
        scene_setup="你刚走进早餐店。",
        raw_content="raw",
        tasks=[
            Task(
                position_index=0,
                prompt="q",
                answer_type="exact",
                expected_answer="a",
                acceptable_answers='["a"]',
            )
        ],
    )
    session.add(scenario)
    await session.commit()
    task = scenario.tasks[0]

    base = datetime.utcnow()
    attempts: list[Attempt] = []
    for i in range(n):
        is_correct = (
            correct_pattern[i] if correct_pattern is not None else (i % 2 == 0)
        )
        a = Attempt(
            task_id=task.id,
            user_answer=f"answer{i}",
            is_correct=is_correct,
            attempted_at=base + timedelta(milliseconds=i),
        )
        session.add(a)
        attempts.append(a)
    await session.commit()
    return attempts


@pytest.mark.asyncio
async def test_history_empty(client: AsyncClient) -> None:
    """Empty DB returns an empty items list and no cursor."""
    resp = await client.get("/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_history_pagination(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """25 attempts paginate cleanly: page 1 has 20, follow cursor to page 2."""
    await _seed_attempts(db_session, n=25)

    page1 = await client.get("/history", params={"limit": 20})
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 20
    assert body1["next_cursor"], "cursor should be present when more pages exist"

    page2 = await client.get(
        "/history", params={"limit": 20, "cursor": body1["next_cursor"]}
    )
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 5
    assert body2["next_cursor"] is None

    # No overlap between pages.
    ids1 = {item["attempt_id"] for item in body1["items"]}
    ids2 = {item["attempt_id"] for item in body2["items"]}
    assert ids1.isdisjoint(ids2)
    assert len(ids1 | ids2) == 25


@pytest.mark.asyncio
async def test_history_filter_incorrect(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """``incorrect_only=true`` returns only attempts with is_correct=False."""
    pattern = [True, False, True, False, False, True, False]
    await _seed_attempts(db_session, n=len(pattern), correct_pattern=pattern)

    resp = await client.get("/history", params={"incorrect_only": True})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == sum(1 for x in pattern if not x)
    assert all(item["is_correct"] is False for item in items)
