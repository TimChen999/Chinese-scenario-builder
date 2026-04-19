"""Image quality filter: cheap binary keep/reject before vision OCR.

Pipeline position (DESIGN.md Section 7): runs after image search +
download, before OCR. The OCR step is by far the most expensive in
the pipeline, so a fast Flash-tier verdict on each candidate keeps
costs down by a large factor.

Prompt strategy: a one-shot system instruction enumerates four
criteria (real photo / Chinese text present / legible / authentic
context) and asks for ``{keep, reason}``. Temperature is 0: this is
a deterministic decision, no creativity wanted.
"""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, Field, ValidationError

from app.agent import _gemini
from app.agent.types import DownloadedImage, FilterVerdict
from app.core.config import Settings
from app.core.prompts import FILTER_SYSTEM, FILTER_USER

# Generation config for the filter call.
FILTER_TEMPERATURE = 0.0
# 512 (not 256) because gemini-2.5-flash can emit a short preamble
# even with response_mime_type=application/json; the extra headroom
# absorbs that without truncating the actual verdict. Thinking is
# auto-disabled by ``_gemini.generate_text`` when a response schema
# is set, so this budget is spent on output, not internal reasoning.
FILTER_MAX_TOKENS = 512
# 45 s because this is a vision call -- we upload image bytes,
# Gemini decodes them, and only then runs the model. Generous
# headroom for slow TLS handshakes, cold starts, or large images.
# The orchestrator's TOTAL_BUDGET_S still bounds the worst case.
FILTER_TIMEOUT_S = 45.0
DEFAULT_BATCH_CONCURRENCY = 5


class FilterError(Exception):
    """Raised when the filter call returns an unusable response."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class FilterResponseSchema(BaseModel):
    """Pydantic mirror of the keep/reject JSON shape."""

    keep: bool = Field(..., description="True if the image should be OCR'd")
    reason: str = Field(..., description="One-sentence explanation, surfaced in logs")


async def filter_image(
    image: DownloadedImage,
    *,
    settings: Settings | None = None,
) -> FilterVerdict:
    """Ask Gemini Flash whether ``image`` is worth OCRing.

    Returns a :class:`FilterVerdict` whose ``keep`` field drives the
    orchestrator's decision; ``reason`` is surfaced in logs / SSE
    progress events so the user understands rejections.

    Raises
    ------
    FilterError
        On invalid JSON, schema mismatch, or any wrapped Gemini
        failure (timeout, transport, missing key).
    """
    contents = [
        FILTER_USER,
        _gemini.make_image_part(image.bytes_, image.mime),
    ]

    try:
        text = await _gemini.generate_text(
            model=_gemini.MODEL_FLASH,
            contents=contents,
            response_schema=FilterResponseSchema,
            system_instruction=FILTER_SYSTEM,
            temperature=FILTER_TEMPERATURE,
            max_output_tokens=FILTER_MAX_TOKENS,
            timeout_s=FILTER_TIMEOUT_S,
            settings=settings,
        )
    except _gemini.GeminiError as exc:
        raise FilterError(f"Filter call failed ({exc.code}): {exc.message}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FilterError(f"Filter response was not valid JSON: {text[:200]}") from exc

    try:
        parsed = FilterResponseSchema.model_validate(data)
    except ValidationError as exc:
        raise FilterError(f"Filter response did not match schema: {exc}") from exc

    return FilterVerdict(image=image, keep=parsed.keep, reason=parsed.reason)


async def filter_images(
    images: list[DownloadedImage],
    *,
    concurrency: int = DEFAULT_BATCH_CONCURRENCY,
    settings: Settings | None = None,
) -> list[FilterVerdict]:
    """Run :func:`filter_image` over a list with bounded parallelism.

    Order-preserving: the i-th element of the returned list is the
    verdict for the i-th input image. Concurrency is capped so we
    never have more than ``concurrency`` Flash calls in flight at
    once (DESIGN.md Section 7 specifies max-5 for filter).

    Per-image failures (timeout, transport error, malformed JSON) are
    converted into a ``keep=False`` verdict whose ``reason`` carries
    the error detail, rather than aborting the whole batch. This
    matches the orchestrator's intent: we only need ``MIN_KEEPERS``
    survivors to proceed, and a transient failure on one image should
    not invalidate the verdicts we already produced for the others.
    The orchestrator's broaden-and-retry path naturally handles the
    case where so many images failed that we drop below MIN_KEEPERS.
    """
    if not images:
        return []

    sem = asyncio.Semaphore(concurrency)

    async def _run(image: DownloadedImage) -> FilterVerdict:
        async with sem:
            try:
                return await filter_image(image, settings=settings)
            except FilterError as exc:
                # Demote the per-image failure to a reject verdict so
                # the surrounding batch can still produce results.
                return FilterVerdict(
                    image=image, keep=False, reason=f"filter failed: {exc.detail}"
                )

    # asyncio.gather preserves the order of its arguments, so we get
    # input-aligned output for free.
    return list(await asyncio.gather(*(_run(img) for img in images)))
