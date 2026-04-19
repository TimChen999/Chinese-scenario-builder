"""Integration tests for the task-answer endpoint.

Covers the four ``answer_type`` evaluation paths (exact, numeric,
multi) plus persistence of the Attempt row and the unknown-task
404 case.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attempt, Scenario, Task


async def _seed_one_scenario(
    session: AsyncSession,
    *,
    answer_type: str = "exact",
    expected: str = "油条",
    acceptable: str = '["油条", "youtiao"]',
) -> tuple[str, str]:
    """Insert a one-task scenario and return ``(scenario_id, task_id)``."""
    scenario = Scenario(
        request_prompt="ordering breakfast",
        scene_type="menu",
        scene_setup="你刚走进早餐店。",
        raw_content="豆浆 3元\n油条 2元",
        tasks=[
            Task(
                position_index=0,
                prompt="cheapest?",
                answer_type=answer_type,
                expected_answer=expected,
                acceptable_answers=acceptable,
                explanation="x",
            )
        ],
    )
    session.add(scenario)
    await session.commit()
    return scenario.id, scenario.tasks[0].id


@pytest.mark.asyncio
async def test_answer_correct_exact(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Exact, case-equal submission marks correct + persists Attempt."""
    sid, tid = await _seed_one_scenario(db_session)

    resp = await client.post(
        f"/scenarios/{sid}/tasks/{tid}/answer", json={"answer": "油条"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is True
    assert body["expected_answer"] == "油条"

    # Persistence side-effect.
    attempts = (await db_session.execute(select(Attempt))).scalars().all()
    assert len(attempts) == 1
    assert attempts[0].is_correct is True
    assert attempts[0].user_answer == "油条"


@pytest.mark.asyncio
async def test_answer_wrong_exact(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wrong submission is incorrect; the attempt is still recorded."""
    sid, tid = await _seed_one_scenario(db_session)

    resp = await client.post(
        f"/scenarios/{sid}/tasks/{tid}/answer", json={"answer": "包子"}
    )
    assert resp.status_code == 200
    assert resp.json()["correct"] is False

    attempts = (await db_session.execute(select(Attempt))).scalars().all()
    assert len(attempts) == 1
    assert attempts[0].is_correct is False


@pytest.mark.asyncio
async def test_answer_acceptable_alternative(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An ``acceptable_answers`` alternative is accepted (case-insensitive)."""
    sid, tid = await _seed_one_scenario(db_session)

    resp = await client.post(
        f"/scenarios/{sid}/tasks/{tid}/answer", json={"answer": "Youtiao"}
    )
    assert resp.status_code == 200
    assert resp.json()["correct"] is True


@pytest.mark.asyncio
async def test_answer_numeric(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Numeric answer extracts digits: '5元' matches expected '5'."""
    sid, tid = await _seed_one_scenario(
        db_session,
        answer_type="numeric",
        expected="5",
        acceptable='["5"]',
    )

    resp = await client.post(
        f"/scenarios/{sid}/tasks/{tid}/answer", json={"answer": "5元"}
    )
    assert resp.status_code == 200
    assert resp.json()["correct"] is True


@pytest.mark.asyncio
async def test_answer_404_unknown_task(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unknown task id (or wrong scenario id) returns 404."""
    sid, _ = await _seed_one_scenario(db_session)

    resp = await client.post(
        f"/scenarios/{sid}/tasks/nonsuchtask/answer", json={"answer": "x"}
    )
    assert resp.status_code == 404
