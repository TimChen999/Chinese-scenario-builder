"""Unit tests for the SQLAlchemy models.

Confirms the relationship + cascade configuration declared in
``app/db/models.py``. See DESIGN.md Step 1 for the named test list.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Attempt, GenerationJob, Scenario, Task


@pytest.mark.asyncio
async def test_scenario_create_and_query(db_session: AsyncSession) -> None:
    """Insert a Scenario with two Tasks and assert the relationship loads."""
    scenario = Scenario(
        request_prompt="ordering breakfast in Beijing",
        scene_type="menu",
        scene_setup="你刚走进一家老北京早餐店。",
        raw_content="豆浆 3元\n油条 2元",
        tasks=[
            Task(
                position_index=0,
                prompt="What is the cheapest item?",
                answer_type="exact",
                expected_answer="油条",
            ),
            Task(
                position_index=1,
                prompt="How much is 豆浆?",
                answer_type="numeric",
                expected_answer="3",
            ),
        ],
    )
    db_session.add(scenario)
    await db_session.commit()

    stmt = (
        select(Scenario)
        .options(selectinload(Scenario.tasks))
        .where(Scenario.id == scenario.id)
    )
    fetched = (await db_session.execute(stmt)).scalar_one()

    assert fetched.request_prompt == "ordering breakfast in Beijing"
    assert fetched.scene_type == "menu"
    assert len(fetched.tasks) == 2
    assert {t.position_index for t in fetched.tasks} == {0, 1}
    assert fetched.tasks[0].position_index == 0  # ordered by position_index
    assert fetched.tasks[0].prompt == "What is the cheapest item?"


@pytest.mark.asyncio
async def test_attempt_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Task should remove its Attempts via cascade."""
    scenario = Scenario(
        request_prompt="prompt",
        scene_type="menu",
        scene_setup="setup",
        raw_content="raw",
    )
    task = Task(
        position_index=0,
        prompt="q",
        answer_type="exact",
        expected_answer="a",
        scenario=scenario,
    )
    attempt_a = Attempt(user_answer="x", is_correct=False, task=task)
    attempt_b = Attempt(user_answer="a", is_correct=True, task=task)
    db_session.add_all([scenario, task, attempt_a, attempt_b])
    await db_session.commit()

    # Sanity: both attempts persisted.
    pre = (await db_session.execute(select(Attempt))).scalars().all()
    assert len(pre) == 2

    await db_session.delete(task)
    await db_session.commit()

    post = (await db_session.execute(select(Attempt))).scalars().all()
    assert post == [], "Attempts should be cascade-deleted with their Task"


@pytest.mark.asyncio
async def test_generation_job_default_status(db_session: AsyncSession) -> None:
    """A freshly constructed GenerationJob defaults to ``status='pending'``."""
    job = GenerationJob(request_prompt="breakfast Beijing")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.status == "pending"
    assert job.scenario_id is None
    assert job.error_message is None
    assert job.completed_at is None
