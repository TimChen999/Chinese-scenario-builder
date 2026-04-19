"""Vision OCR stage: extract verbatim Chinese text from an image.

Pipeline position (DESIGN.md Section 7): runs on each filtered
candidate image. We pick the result with the highest reported
confidence + most extracted text and feed it to the assembly stage.

Prompt strategy: a system instruction (see ``prompts.OCR_SYSTEM``)
locks the output to a strict JSON shape. The user message asks the
model to extract every visible character verbatim. Temperature is
0.2 -- low but non-zero -- so the model can disambiguate ambiguous
characters from context without veering into creative paraphrase.

Authenticity invariant (Section 1, Section 5): the ``raw_text`` we
return is the sole source of truth for what the user reads. No
downstream code is permitted to alter it.
"""

from __future__ import annotations

import json
from io import BytesIO

from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from app.agent import _gemini
from app.agent.types import DownloadedImage, OcrResult
from app.core.config import Settings
from app.core.prompts import OCR_SYSTEM, OCR_USER

# Anything above this we resize before sending. Gemini accepts ~20 MB
# inline but smaller payloads are cheaper, faster, and avoid SDK edge
# cases. 4 MB matches DESIGN.md Step 3.
MAX_INLINE_BYTES = 4 * 1024 * 1024
MAX_LONGEST_SIDE_PX = 1568

# Generation config for the OCR call.
OCR_TEMPERATURE = 0.2
OCR_MAX_TOKENS = 4096
# 90 s: this is the most expensive call in the pipeline (Gemini Pro,
# vision, dense Chinese text). Real-world OCR on a busy menu can take
# 30-60 s end to end; the extra headroom absorbs Pro tail latency
# without forcing the orchestrator to give up prematurely.
OCR_TIMEOUT_S = 90.0


class OcrError(Exception):
    """Raised when the OCR call returns an unusable response.

    Includes invalid JSON, schema mismatch, and underlying transport
    failures (re-raised from :class:`_gemini.GeminiError` to keep
    callers free of SDK details).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class OcrResponseSchema(BaseModel):
    """Pydantic mirror of the OCR JSON shape declared in ``OCR_SYSTEM``.

    Defined here (not in ``app/schemas``) because it is an
    LLM-response schema, not an HTTP contract. The Gemini SDK
    accepts this directly as ``response_schema`` to enforce JSON mode.
    """

    raw_text: str = Field(..., description="OCR'd text, verbatim")
    confidence: float = Field(..., ge=0.0, le=1.0)
    scene_type: str = Field(..., description="menu | sign | notice | map | label | instruction | other")
    notes: str | None = Field(default=None)


def _resize_if_needed(image: DownloadedImage) -> DownloadedImage:
    """Return ``image`` unchanged if small enough, else a downsized JPEG copy.

    We resize before sending to keep the request under
    :data:`MAX_INLINE_BYTES` and to reduce vision token cost. Aspect
    ratio is preserved; output is JPEG (quality 85) regardless of
    input format because JPEG gives the best size/quality tradeoff
    for photographs of menus and signs.
    """
    if len(image.bytes_) <= MAX_INLINE_BYTES:
        return image

    pil_image = Image.open(BytesIO(image.bytes_))
    if pil_image.mode not in ("RGB", "L"):
        pil_image = pil_image.convert("RGB")

    w, h = pil_image.size
    longest = max(w, h)
    if longest > MAX_LONGEST_SIDE_PX:
        scale = MAX_LONGEST_SIDE_PX / longest
        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        pil_image = pil_image.resize(new_size, Image.LANCZOS)

    buf = BytesIO()
    pil_image.save(buf, format="JPEG", quality=85, optimize=True)
    return DownloadedImage(
        bytes_=buf.getvalue(),
        mime="image/jpeg",
        original=image.original,
    )


async def extract_text(
    image: DownloadedImage,
    *,
    settings: Settings | None = None,
) -> OcrResult:
    """Run vision OCR on ``image`` and return the parsed :class:`OcrResult`.

    Steps:
      1. Resize if larger than :data:`MAX_INLINE_BYTES`.
      2. Build the multipart ``contents`` (user instruction + image part).
      3. Call Gemini Pro in JSON mode with :class:`OcrResponseSchema`.
      4. Parse + validate the response.
      5. Map to :class:`OcrResult` (renaming ``scene_type`` ->
         ``scene_type_guess`` to reflect that the model is *guessing*
         the type from a single image).

    Raises
    ------
    OcrError
        On invalid JSON, schema mismatch, or any wrapped Gemini failure.
    """
    prepared = _resize_if_needed(image)

    contents = [
        OCR_USER,
        _gemini.make_image_part(prepared.bytes_, prepared.mime),
    ]

    try:
        text = await _gemini.generate_text(
            model=_gemini.MODEL_PRO,
            contents=contents,
            response_schema=OcrResponseSchema,
            system_instruction=OCR_SYSTEM,
            temperature=OCR_TEMPERATURE,
            max_output_tokens=OCR_MAX_TOKENS,
            timeout_s=OCR_TIMEOUT_S,
            settings=settings,
        )
    except _gemini.GeminiError as exc:
        raise OcrError(f"Vision call failed ({exc.code}): {exc.message}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OcrError(f"Vision response was not valid JSON: {text[:200]}") from exc

    try:
        parsed = OcrResponseSchema.model_validate(data)
    except ValidationError as exc:
        raise OcrError(f"Vision response did not match schema: {exc}") from exc

    return OcrResult(
        image=prepared,
        raw_text=parsed.raw_text,
        confidence=parsed.confidence,
        scene_type_guess=parsed.scene_type,
        notes=parsed.notes,
    )
