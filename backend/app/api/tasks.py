"""Task answer endpoint.

Single route mounted under ``/scenarios/{scenario_id}/tasks``:

* ``POST /scenarios/{scenario_id}/tasks/{task_id}/answer``
  Evaluates the user's submission, persists an ``Attempt`` row, and
  returns an :class:`AnswerResult` so the UI can show right/wrong
  + explanation immediately.

Answer-evaluation rules (DESIGN.md Section 6 + Step 7):

* ``exact``   -- case-insensitive trimmed comparison against
  ``expected_answer`` and any ``acceptable_answers``.
* ``numeric`` -- extract the first signed decimal number from the
  user's answer; equality compare against the same extraction from
  each acceptable answer.
* ``multi``   -- user input is split by comma; correct if the set
  matches any acceptable's split set (case-insensitive, trimmed).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.scenarios import parse_acceptable_answers
from app.db.models import Attempt, Task
from app.schemas.task import AnswerResult, TaskAnswerRequest

router = APIRouter(prefix="/scenarios/{scenario_id}/tasks", tags=["tasks"])

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _to_number(text: str) -> float | None:
    """Return the first signed decimal number found in ``text``, or None.

    Lets us compare "5", "5元", "￥5.00", "the answer is 5" all as 5.
    """
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def evaluate_answer(task: Task, user_answer: str) -> bool:
    """Return True if ``user_answer`` matches ``task`` per its ``answer_type``.

    Pure function over the Task row + the user string; isolated so
    unit tests can exercise it without touching the database.
    """
    user = user_answer.strip()
    if not user:
        return False

    candidates = [task.expected_answer, *parse_acceptable_answers(task.acceptable_answers)]

    if task.answer_type == "exact":
        user_cf = user.casefold()
        return any(c.strip().casefold() == user_cf for c in candidates)

    if task.answer_type == "numeric":
        user_num = _to_number(user)
        if user_num is None:
            return False
        for c in candidates:
            c_num = _to_number(c)
            if c_num is not None and c_num == user_num:
                return True
        return False

    if task.answer_type == "multi":
        user_set = {p.strip().casefold() for p in user.split(",") if p.strip()}
        if not user_set:
            return False
        for c in candidates:
            cand_set = {p.strip().casefold() for p in c.split(",") if p.strip()}
            if cand_set == user_set:
                return True
        return False

    # Unknown answer_type -- treat as wrong rather than crash.
    return False


@router.post("/{task_id}/answer", response_model=AnswerResult)
async def submit_answer(
    scenario_id: str,
    task_id: str,
    body: TaskAnswerRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AnswerResult:
    """Evaluate a submission, persist the Attempt, and return the verdict."""
    task = await session.get(Task, task_id)
    if task is None or task.scenario_id != scenario_id:
        raise HTTPException(status_code=404, detail="task not found")

    correct = evaluate_answer(task, body.answer)
    attempt = Attempt(task_id=task.id, user_answer=body.answer, is_correct=correct)
    session.add(attempt)
    await session.commit()

    return AnswerResult(
        correct=correct,
        expected_answer=task.expected_answer,
        acceptable_answers=parse_acceptable_answers(task.acceptable_answers),
        explanation=task.explanation,
    )
