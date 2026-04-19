"""``GET /history`` -- cursor-paginated list of past attempts.

See DESIGN.md Section 6 for the request/response contract.

Joins Attempt -> Task -> Scenario so each row carries enough context
to render in the History UI without a follow-up fetch.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_db_session
from app.db.models import Attempt, Task
from app.schemas.job import HistoryItem, HistoryListResponse

router = APIRouter(prefix="/history", tags=["history"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@router.get("", response_model=HistoryListResponse)
async def list_history(
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
    correct_only: bool = Query(default=False),
    incorrect_only: bool = Query(default=False),
) -> HistoryListResponse:
    """Return attempts newest-first, optionally filtered by correctness.

    ``correct_only`` and ``incorrect_only`` are mutually exclusive
    in practice; if both are true we ignore both (silently) rather
    than 400 since the call is harmless.
    """
    stmt = (
        select(Attempt)
        .options(joinedload(Attempt.task).joinedload(Task.scenario))
        .order_by(Attempt.attempted_at.desc(), Attempt.id.desc())
    )

    if correct_only and not incorrect_only:
        stmt = stmt.where(Attempt.is_correct.is_(True))
    elif incorrect_only and not correct_only:
        stmt = stmt.where(Attempt.is_correct.is_(False))

    if cursor:
        try:
            cursor_id = int(cursor)
        except ValueError:
            cursor_id = None
        if cursor_id is not None:
            cursor_row = await session.get(Attempt, cursor_id)
            if cursor_row is not None:
                stmt = stmt.where(
                    (Attempt.attempted_at < cursor_row.attempted_at)
                    | (
                        (Attempt.attempted_at == cursor_row.attempted_at)
                        & (Attempt.id < cursor_id)
                    )
                )

    # Over-fetch by one: lets us know if there's a next page without
    # a follow-up COUNT query. The cursor is the id of the LAST item
    # actually returned (not the over-fetched peek), so the next call
    # walks strictly past it.
    stmt = stmt.limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = str(page[-1].id) if has_more and page else None

    items = [
        HistoryItem(
            attempt_id=a.id,
            task_id=a.task.id,
            scenario_id=a.task.scenario.id,
            scenario_title=a.task.scenario.request_prompt,
            task_prompt=a.task.prompt,
            user_answer=a.user_answer,
            expected_answer=a.task.expected_answer,
            is_correct=a.is_correct,
            attempted_at=a.attempted_at,
        )
        for a in page
    ]
    return HistoryListResponse(items=items, next_cursor=next_cursor)
