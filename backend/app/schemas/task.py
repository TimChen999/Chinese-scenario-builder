"""Task + answer-related HTTP schemas.

See DESIGN.md Section 5 (`AnswerResult` JSON shape) and Section 6
(`POST /scenarios/{id}/tasks/{task_id}/answer`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskOut(BaseModel):
    """Task as exposed to the frontend.

    Note: ``expected_answer`` and ``acceptable_answers`` are NOT
    returned in this shape; they would let the user cheat by reading
    the network panel. They are only returned in :class:`AnswerResult`
    after a submission.
    """

    id: str
    position_index: int
    prompt: str
    answer_type: str
    explanation: str | None = None


class TaskAnswerRequest(BaseModel):
    """POST body for the answer endpoint."""

    answer: str = Field(..., description="The user's submitted answer string")


class AnswerResult(BaseModel):
    """Response from the answer endpoint.

    Includes the canonical answer + acceptable variants so the
    frontend can show "Expected: X" + the explanation regardless of
    whether the user got it right.
    """

    correct: bool
    expected_answer: str
    acceptable_answers: list[str]
    explanation: str | None = None
