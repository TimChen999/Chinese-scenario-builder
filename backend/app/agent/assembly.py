"""Scenario assembly stage: turn raw OCR text into a teachable scene.

Pipeline position (DESIGN.md Section 7): the final LLM call before
persistence. Inputs are the chosen :class:`OcrResult` plus the
user's original prompt and any hints; output is a
:class:`ScenarioDraft` that the API layer turns into Scenario + Task
DB rows.

Prompt strategy: a system instruction (``ASSEMBLY_SYSTEM``)
enumerates the rules; a user message (``ASSEMBLY_USER``) interpolates
the runtime inputs. Temperature is 0.7 -- higher than OCR -- so the
``scene_setup`` paragraph reads naturally, but the JSON shape is
still enforced via ``response_schema``.

Authenticity invariant (Section 1, Section 5): the ``raw_content``
field of the returned draft is byte-for-byte the OCR's ``raw_text``.
Even if the model accidentally echoes a modified version inside its
own JSON, we never use that -- we always pass the OCR text through
verbatim. The unit test ``test_raw_content_preserved`` guards this.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.agent import _gemini
from app.agent.types import OcrResult, ScenarioDraft, TaskDraft
from app.agent.validators import AssemblyResponseSchema
from app.core.config import Settings
from app.core.prompts import ASSEMBLY_SYSTEM, ASSEMBLY_USER

# Generation config for the assembly call.
ASSEMBLY_TEMPERATURE = 0.7
ASSEMBLY_MAX_TOKENS = 4096
ASSEMBLY_TIMEOUT_S = 30.0


class AssemblyError(Exception):
    """Raised when the assembly LLM call fails or returns unusable output.

    Covers invalid JSON, schema mismatch (including custom validator
    failures like "no Chinese in scene_setup"), and wrapped Gemini
    transport / timeout errors.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def assemble(
    ocr_result: OcrResult,
    request_prompt: str,
    *,
    region: str | None = None,
    format_hint: str | None = None,
    settings: Settings | None = None,
) -> ScenarioDraft:
    """Build a :class:`ScenarioDraft` from an :class:`OcrResult`.

    Parameters
    ----------
    ocr_result
        The OCR pass we picked as best-effort representation of the
        source image. ``raw_text`` is treated as ground truth.
    request_prompt
        The user's original natural-language prompt (e.g. "ordering
        breakfast in Beijing"). Helps the model contextualise the
        scene.
    region, format_hint
        Optional hints; passed through to the LLM via the
        ``ASSEMBLY_USER`` template, but never overrule ``raw_text``.
    settings
        Test injection point.

    Raises
    ------
    AssemblyError
        On any LLM failure or response that fails validation.

    Returns
    -------
    A :class:`ScenarioDraft` whose ``raw_content`` is byte-identical
    to ``ocr_result.raw_text`` and whose ``source_image`` is the same
    :class:`DownloadedImage` that produced the OCR.
    """
    user_message = ASSEMBLY_USER.format(
        user_request=request_prompt,
        scene_type=ocr_result.scene_type_guess,
        region=region or "(unspecified)",
        format_hint=format_hint or "(any)",
        raw_text=ocr_result.raw_text,
    )

    try:
        text = await _gemini.generate_text(
            model=_gemini.MODEL_PRO,
            contents=[user_message],
            response_schema=AssemblyResponseSchema,
            system_instruction=ASSEMBLY_SYSTEM,
            temperature=ASSEMBLY_TEMPERATURE,
            max_output_tokens=ASSEMBLY_MAX_TOKENS,
            timeout_s=ASSEMBLY_TIMEOUT_S,
            settings=settings,
        )
    except _gemini.GeminiError as exc:
        raise AssemblyError(f"Assembly call failed ({exc.code}): {exc.message}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssemblyError(
            f"Assembly response was not valid JSON: {text[:200]}"
        ) from exc

    try:
        parsed = AssemblyResponseSchema.model_validate(data)
    except ValidationError as exc:
        raise AssemblyError(f"Assembly response did not match schema: {exc}") from exc

    return ScenarioDraft(
        scene_type=ocr_result.scene_type_guess,
        scene_setup=parsed.scene_setup,
        # CRITICAL: raw_content comes from OCR, NEVER from the assembly
        # LLM. Authenticity invariant -- DESIGN.md Section 1.
        raw_content=ocr_result.raw_text,
        tasks=[
            TaskDraft(
                prompt=t.prompt,
                answer_type=t.answer_type,
                expected_answer=t.expected_answer,
                acceptable_answers=list(t.acceptable_answers),
                explanation=t.explanation,
            )
            for t in parsed.tasks
        ],
        source_image=ocr_result.image,
    )
