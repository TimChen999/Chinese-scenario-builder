"""Pydantic schemas + custom validators for the assembly stage's LLM output.

Two responsibilities:

* Mirror the JSON shape declared in ``ASSEMBLY_SYSTEM`` so the
  ``google-genai`` SDK can use it as ``response_schema`` and force
  the model into structured output.
* Catch the failure modes that response-schema enforcement alone does
  not (e.g. "scene_setup must contain at least one Chinese character",
  "acceptable_answers must include expected_answer").

Lives in ``app.agent`` rather than ``app.schemas`` because these are
LLM-response shapes, not HTTP contracts. The HTTP-facing schemas
arrive in Step 7 under ``app/schemas/``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Two ranges cover the vast majority of real-world Chinese characters
# without false-positives on Latin / digit / punctuation runs:
# * 0x4E00..0x9FFF -- CJK Unified Ideographs (modern + classical)
# * 0x3400..0x4DBF -- CJK Extension A (rare characters)
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
)


def has_cjk(text: str) -> bool:
    """Return True if ``text`` contains at least one CJK ideograph.

    Used by :class:`AssemblyResponseSchema` to verify the LLM did not
    quietly answer with English-only prose -- a common failure mode
    when the prompt is paraphrased.
    """
    for ch in text:
        cp = ord(ch)
        for low, high in _CJK_RANGES:
            if low <= cp <= high:
                return True
    return False


class TaskResponseSchema(BaseModel):
    """One task in the LLM's assembly response.

    The ``acceptable_answers`` field is auto-corrected to always
    include ``expected_answer`` -- a more lenient policy than rejecting
    the whole response, since "accept the canonical answer too" is
    obviously what the user wants and is cheaper than another LLM
    round-trip (DESIGN.md Step 5 plan note).
    """

    prompt: str = Field(..., min_length=1)
    answer_type: Literal["exact", "numeric", "multi"]
    expected_answer: str = Field(..., min_length=1)
    acceptable_answers: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @model_validator(mode="after")
    def _ensure_acceptable_includes_expected(self) -> TaskResponseSchema:
        """Append ``expected_answer`` to ``acceptable_answers`` if missing."""
        if self.expected_answer not in self.acceptable_answers:
            self.acceptable_answers = [*self.acceptable_answers, self.expected_answer]
        return self


class AssemblyResponseSchema(BaseModel):
    """Top-level shape returned by the assembly LLM call.

    ``min_length=1, max_length=5`` on tasks matches DESIGN.md Section 7
    (the design says "EXACTLY 3" but allows 1-5 from the validator's
    perspective; the orchestrator can retry if the count is uncomfortable).
    """

    scene_setup: str = Field(..., min_length=1)
    tasks: list[TaskResponseSchema] = Field(..., min_length=1, max_length=5)

    @field_validator("scene_setup")
    @classmethod
    def _scene_setup_has_chinese(cls, value: str) -> str:
        """Reject English-only setups; the user came here for Chinese."""
        if not has_cjk(value):
            raise ValueError("scene_setup must contain at least one Chinese character")
        return value
