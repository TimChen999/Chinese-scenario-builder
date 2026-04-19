"""Agent orchestrator: end-to-end "prompt -> ScenarioDraft" pipeline.

Wires the four stage modules (``search``, ``filter``, ``vision``,
``assembly``) together with the retry, parallelism, and progress
semantics from DESIGN.md Section 7. The API layer (Step 7) calls
:func:`run_generation` from a background task and forwards
``on_progress`` events to the SSE stream.

Stage emit order (matches DESIGN.md exactly):

    queries_generated
    images_searched
    images_downloaded
    images_filtered
    ocr_in_progress
    assembling
    done

Retry policy (also from Section 7):

* If the filter stage yields fewer than ``MIN_KEEPERS`` images and we
  still have attempts left, ask Flash to broaden the queries and
  re-run search.
* If assembly raises a validation error and we still have OCR results
  in reserve, retry assembly with the next-best OCR result.

Total wall-clock budget is enforced via :func:`asyncio.wait_for`.
On exceeding the budget we raise :class:`GenerationFailed` with
stage ``"timeout"``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agent import _gemini, assembly, search, vision
from app.agent import filter as filter_mod
from app.agent.assembly import AssemblyError
from app.agent.types import (
    DownloadedImage,
    FilterVerdict,
    ImageResult,
    OcrResult,
    ScenarioDraft,
)
from app.agent.vision import OcrError
from app.core.config import Settings
from app.core.prompts import (
    BROADEN_QUERIES_SYSTEM,
    BROADEN_QUERIES_USER,
    SEARCH_QUERIES_SYSTEM,
    SEARCH_QUERIES_USER,
)
from app.services import image_store
from app.services.image_store import ImageDownloadError

# ─── Tunables (mirrored in DESIGN.md Section 7) ────────────────────
SEARCH_CONCURRENCY = 3
DOWNLOAD_CONCURRENCY = 5
FILTER_CONCURRENCY = 5
OCR_CONCURRENCY = 3
DEFAULT_IMAGES_PER_QUERY = 6
MAX_DOWNLOADS = 10
MAX_OCR_INPUTS = 3
MIN_KEEPERS = 2
MAX_FILTER_ATTEMPTS = 2
MAX_ASSEMBLY_ATTEMPTS = 2
TOTAL_BUDGET_S = 120.0

# ─── Public callback type ──────────────────────────────────────────
ProgressCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class GenerationFailed(Exception):
    """Single error type raised by :func:`run_generation`.

    ``stage`` identifies which pipeline phase ran out of budget /
    retries (``"queries"``, ``"search"``, ``"filter"``, ``"ocr"``,
    ``"assembly"``, ``"timeout"``). The API layer surfaces both
    fields in the ``failed`` SSE event and the JobStatus row.
    """

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


# ─── Search-query generation helpers ───────────────────────────────


class _QueriesSchema(BaseModel):
    """Pydantic mirror of ``{"queries": [...]}`` for the Flash calls."""

    queries: list[str] = Field(..., min_length=1, max_length=5)


async def _generate_search_queries(
    prompt: str,
    *,
    scene_hint: str | None,
    region: str | None,
    settings: Settings | None = None,
) -> list[str]:
    """Ask Gemini Flash for 3 Chinese-language image-search queries.

    See ``SEARCH_QUERIES_SYSTEM`` for the wording strategy. Falls
    back to one trivial query (the user prompt itself) if the LLM
    call fails -- a degraded path is better than aborting the
    whole pipeline at stage 1.
    """
    user_msg = SEARCH_QUERIES_USER.format(
        prompt=prompt,
        scene_hint=scene_hint or "(any)",
        region=region or "(unspecified)",
    )
    try:
        text = await _gemini.generate_text(
            model=_gemini.MODEL_FLASH,
            contents=[user_msg],
            response_schema=_QueriesSchema,
            system_instruction=SEARCH_QUERIES_SYSTEM,
            temperature=0.3,
            max_output_tokens=512,
            timeout_s=15.0,
            settings=settings,
        )
        return _QueriesSchema.model_validate(json.loads(text)).queries
    except (_gemini.GeminiError, json.JSONDecodeError, ValidationError) as exc:
        raise GenerationFailed("queries", f"could not generate search queries: {exc}") from exc


async def _broaden_queries(
    prompt: str,
    *,
    prev_queries: list[str],
    scene_hint: str | None,
    region: str | None,
    settings: Settings | None = None,
) -> list[str]:
    """Ask Flash for broader queries when the filter stage starves."""
    user_msg = BROADEN_QUERIES_USER.format(
        prompt=prompt,
        prev_queries=json.dumps(prev_queries, ensure_ascii=False),
        scene_hint=scene_hint or "(any)",
        region=region or "(unspecified)",
    )
    try:
        text = await _gemini.generate_text(
            model=_gemini.MODEL_FLASH,
            contents=[user_msg],
            response_schema=_QueriesSchema,
            system_instruction=BROADEN_QUERIES_SYSTEM,
            temperature=0.5,
            max_output_tokens=512,
            timeout_s=15.0,
            settings=settings,
        )
        return _QueriesSchema.model_validate(json.loads(text)).queries
    except (_gemini.GeminiError, json.JSONDecodeError, ValidationError):
        # Falling back to the original queries is harmless -- the next
        # search attempt will use them and likely fail again, leading
        # to a clean GenerationFailed("filter", ...).
        return prev_queries


# ─── Stage helpers (parallelism + error swallowing) ────────────────


async def _run_search(
    queries: list[str], settings: Settings | None
) -> list[ImageResult]:
    """Search each query in parallel; dedupe results by URL.

    Per-query failures are swallowed (we still want any results from
    the other queries). If ALL queries fail the returned list is
    empty -- the caller decides whether that's fatal.
    """
    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def _one(q: str) -> list[ImageResult]:
        async with sem:
            try:
                return await search.search_images(
                    q, limit=DEFAULT_IMAGES_PER_QUERY, settings=settings
                )
            except search.SearchError:
                return []

    grouped = await asyncio.gather(*(_one(q) for q in queries))
    results: list[ImageResult] = []
    seen: set[str] = set()
    for batch in grouped:
        for r in batch:
            if r.url in seen:
                continue
            seen.add(r.url)
            results.append(r)
    return results


async def _download_many(images: list[ImageResult]) -> list[DownloadedImage]:
    """Download up to :data:`MAX_DOWNLOADS` images in parallel; skip failures.

    A handful of dead URLs is the rule rather than the exception with
    open-web image search, so we deliberately silence per-image errors
    and let the count downstream decide whether to retry.
    """
    sem = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

    async def _one(img: ImageResult) -> DownloadedImage | None:
        async with sem:
            try:
                return await image_store.download_image(img)
            except ImageDownloadError:
                return None

    results = await asyncio.gather(*(_one(i) for i in images[:MAX_DOWNLOADS]))
    return [r for r in results if r is not None]


async def _ocr_many(
    images: list[DownloadedImage], settings: Settings | None
) -> list[OcrResult]:
    """OCR up to :data:`MAX_OCR_INPUTS` images in parallel."""
    sem = asyncio.Semaphore(OCR_CONCURRENCY)

    async def _one(img: DownloadedImage) -> OcrResult | None:
        async with sem:
            try:
                return await vision.extract_text(img, settings=settings)
            except OcrError:
                return None

    results = await asyncio.gather(*(_one(i) for i in images[:MAX_OCR_INPUTS]))
    return [r for r in results if r is not None]


def _ocr_score(result: OcrResult) -> float:
    """Combined heuristic: confidence * text length.

    Both signals matter. A high-confidence OCR of one character is
    less useful than a moderately confident OCR of a full menu, and
    vice versa.
    """
    return result.confidence * len(result.raw_text)


def _sort_ocr_for_assembly(results: list[OcrResult]) -> list[OcrResult]:
    """Sort OCR results best -> worst so the assembly retry walks a queue."""
    return sorted(results, key=_ocr_score, reverse=True)


# ─── Public entry point ────────────────────────────────────────────


async def run_generation(
    request_prompt: str,
    *,
    scene_hint: str | None = None,
    region: str | None = None,
    format_hint: str | None = None,
    on_progress: ProgressCallback | None = None,
    settings: Settings | None = None,
) -> ScenarioDraft:
    """Run the full agent pipeline and return a :class:`ScenarioDraft`.

    Parameters
    ----------
    request_prompt
        The user's natural-language scenario request (e.g. "ordering
        breakfast in Beijing"). Passed to both the query-generation
        and assembly LLM calls.
    scene_hint, region, format_hint
        Optional hints that flow into the LLM prompts. None is fine.
    on_progress
        Optional async callback ``(stage, detail) -> None``. Invoked
        once per stage transition; the API layer uses it to fan out
        SSE events.
    settings
        Test injection point.

    Raises
    ------
    GenerationFailed
        With a ``stage`` identifying which phase exhausted retries
        or budget. Always raised within the 120 s wall-clock budget;
        on exceeding the budget the stage is ``"timeout"``.
    """

    async def _emit(stage: str, **detail: Any) -> None:
        if on_progress is not None:
            await on_progress(stage, detail)

    async def _flow() -> ScenarioDraft:
        queries = await _generate_search_queries(
            request_prompt,
            scene_hint=scene_hint,
            region=region,
            settings=settings,
        )
        await _emit("queries_generated", queries=queries)

        keepers: list[FilterVerdict] = []
        for attempt in range(MAX_FILTER_ATTEMPTS):
            search_results = await _run_search(queries, settings)
            await _emit("images_searched", count=len(search_results))

            downloaded = await _download_many(search_results)
            await _emit("images_downloaded", count=len(downloaded))

            verdicts = await filter_mod.filter_images(
                downloaded, concurrency=FILTER_CONCURRENCY, settings=settings
            )
            keepers = [v for v in verdicts if v.keep]
            await _emit("images_filtered", kept=len(keepers), total=len(verdicts))

            if len(keepers) >= MIN_KEEPERS:
                break

            if attempt + 1 >= MAX_FILTER_ATTEMPTS:
                raise GenerationFailed(
                    "filter",
                    (
                        f"only {len(keepers)} usable image(s) found after "
                        f"{attempt + 1} attempt(s)"
                    ),
                )
            queries = await _broaden_queries(
                request_prompt,
                prev_queries=queries,
                scene_hint=scene_hint,
                region=region,
                settings=settings,
            )

        ocr_inputs = [v.image for v in keepers[:MAX_OCR_INPUTS]]
        await _emit("ocr_in_progress", count=len(ocr_inputs))
        ocrs = await _ocr_many(ocr_inputs, settings)
        if not ocrs:
            raise GenerationFailed("ocr", "no OCR result succeeded on any kept image")

        ocrs_sorted = _sort_ocr_for_assembly(ocrs)
        await _emit("assembling")

        last_error: AssemblyError | None = None
        for ocr in ocrs_sorted[:MAX_ASSEMBLY_ATTEMPTS]:
            try:
                draft = await assembly.assemble(
                    ocr,
                    request_prompt,
                    region=region,
                    format_hint=format_hint,
                    settings=settings,
                )
            except AssemblyError as exc:
                last_error = exc
                continue
            await _emit("done")
            return draft

        # All assembly attempts raised.
        detail = str(last_error.detail) if last_error else "unknown"
        raise GenerationFailed("assembly", f"all attempts failed: {detail}")

    try:
        return await asyncio.wait_for(_flow(), timeout=TOTAL_BUDGET_S)
    except TimeoutError as exc:
        raise GenerationFailed(
            "timeout", f"total budget {TOTAL_BUDGET_S}s exceeded"
        ) from exc
