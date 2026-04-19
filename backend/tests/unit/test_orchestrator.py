"""Unit tests for ``app.agent.orchestrator``.

We monkeypatch the four stage modules + helper LLM calls so the
tests run in milliseconds without touching network. Each test
constructs the smallest set of fakes it needs and asserts on the
specific behaviour under test (retries, ordering, timeout).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.agent import orchestrator
from app.agent.assembly import AssemblyError
from app.agent.orchestrator import GenerationFailed, run_generation
from app.agent.types import (
    DownloadedImage,
    FilterVerdict,
    ImageResult,
    OcrResult,
    ScenarioDraft,
    TaskDraft,
)
from app.agent.vision import OcrError

# ─── Fake constructors ────────────────────────────────────────────


def _image_result(label: str) -> ImageResult:
    return ImageResult(
        url=f"https://example.com/{label}.jpg",
        title=label,
        source_page_url="https://example.com",
        width=800,
        height=600,
    )


def _downloaded(label: str) -> DownloadedImage:
    return DownloadedImage(
        bytes_=b"fake-bytes",
        mime="image/jpeg",
        original=_image_result(label),
    )


def _ocr(label: str, *, raw: str = "豆浆 3元\n油条 2元", confidence: float = 0.9) -> OcrResult:
    return OcrResult(
        image=_downloaded(label),
        raw_text=raw,
        confidence=confidence,
        scene_type_guess="menu",
        notes=None,
    )


def _draft(image: DownloadedImage, raw: str = "豆浆 3元\n油条 2元") -> ScenarioDraft:
    return ScenarioDraft(
        scene_type="menu",
        scene_setup="你刚走进早餐店。",
        raw_content=raw,
        tasks=[
            TaskDraft(
                prompt="cheapest?",
                answer_type="exact",
                expected_answer="油条",
                acceptable_answers=["油条"],
                explanation="2元",
            )
        ],
        source_image=image,
    )


# ─── Patch helpers ────────────────────────────────────────────────


def _patch_queries(monkeypatch: pytest.MonkeyPatch, queries: list[str]) -> None:
    async def fake(*_args, **_kwargs):
        return queries

    monkeypatch.setattr(orchestrator, "_generate_search_queries", fake)


def _patch_broaden(monkeypatch: pytest.MonkeyPatch, queries: list[str]) -> list[int]:
    """Patch query broadening; returns a counter list (mutated on each call)."""
    counter: list[int] = []

    async def fake(*_args, **_kwargs):
        counter.append(1)
        return queries

    monkeypatch.setattr(orchestrator, "_broaden_queries", fake)
    return counter


def _patch_search(
    monkeypatch: pytest.MonkeyPatch, results_per_query: list[ImageResult]
) -> None:
    async def fake(query, *, limit=10, settings=None):
        return list(results_per_query)

    monkeypatch.setattr(orchestrator.search, "search_images", fake)


def _patch_download_all_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(image, **_kwargs):
        return DownloadedImage(
            bytes_=b"fake", mime="image/jpeg", original=image
        )

    monkeypatch.setattr(orchestrator.image_store, "download_image", fake)


def _patch_filter(
    monkeypatch: pytest.MonkeyPatch,
    decisions: Callable[[DownloadedImage], bool] | list[bool],
) -> None:
    async def fake(images, *, concurrency=5, settings=None):
        verdicts = []
        for i, img in enumerate(images):
            if callable(decisions):
                keep = decisions(img)
            elif i < len(decisions):
                keep = decisions[i]
            else:
                keep = False
            verdicts.append(FilterVerdict(image=img, keep=keep, reason="ok" if keep else "no"))
        return verdicts

    monkeypatch.setattr(orchestrator.filter_mod, "filter_images", fake)


def _patch_ocr(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[DownloadedImage], OcrResult] | OcrResult,
    delay_s: float = 0.0,
) -> None:
    async def fake(img: DownloadedImage, *, settings=None) -> OcrResult:
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        if callable(factory):
            return factory(img)
        return factory

    monkeypatch.setattr(orchestrator.vision, "extract_text", fake)


def _patch_assembly(
    monkeypatch: pytest.MonkeyPatch,
    behaviour: Callable[[OcrResult], Awaitable[ScenarioDraft]],
) -> list[OcrResult]:
    """Replace assembly.assemble; return the list of OCRs it was called with."""
    called_with: list[OcrResult] = []

    async def fake(ocr, request_prompt, *, region=None, format_hint=None, settings=None):
        called_with.append(ocr)
        return await behaviour(ocr)

    monkeypatch.setattr(orchestrator.assembly, "assemble", fake)
    return called_with


# ─── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """All stages succeed; orchestrator returns a ScenarioDraft."""
    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(4)])
    _patch_download_all_succeed(monkeypatch)
    _patch_filter(monkeypatch, lambda img: True)  # all keep

    async def fake_ocr(img, *, settings=None):
        return _ocr(img.original.title)

    monkeypatch.setattr(orchestrator.vision, "extract_text", fake_ocr)

    async def fake_assembly(ocr):
        return _draft(ocr.image, raw=ocr.raw_text)

    _patch_assembly(monkeypatch, fake_assembly)

    stages: list[str] = []

    async def on_progress(stage: str, detail: dict[str, Any]) -> None:
        stages.append(stage)

    draft = await run_generation(
        "ordering breakfast in Beijing",
        on_progress=on_progress,
    )

    assert isinstance(draft, ScenarioDraft)
    assert draft.scene_type == "menu"
    assert draft.raw_content == "豆浆 3元\n油条 2元"
    assert stages == [
        "queries_generated",
        "images_searched",
        "images_downloaded",
        "images_filtered",
        "ocr_in_progress",
        "assembling",
        "done",
    ]


@pytest.mark.asyncio
async def test_retries_on_few_keepers(monkeypatch: pytest.MonkeyPatch) -> None:
    """First filter pass yields 0 keepers; broaden + retry yields 3."""
    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    broaden_counter = _patch_broaden(monkeypatch, ["broad1", "broad2", "broad3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(3)])
    _patch_download_all_succeed(monkeypatch)

    # First call -> all reject, second -> all keep.
    call_count = {"n": 0}

    async def fake_filter(images, *, concurrency=5, settings=None):
        call_count["n"] += 1
        keep = call_count["n"] >= 2
        return [
            FilterVerdict(image=img, keep=keep, reason="ok" if keep else "no")
            for img in images
        ]

    monkeypatch.setattr(orchestrator.filter_mod, "filter_images", fake_filter)

    async def fake_ocr(img, *, settings=None):
        return _ocr(img.original.title)

    monkeypatch.setattr(orchestrator.vision, "extract_text", fake_ocr)

    async def fake_assembly(ocr):
        return _draft(ocr.image)

    _patch_assembly(monkeypatch, fake_assembly)

    draft = await run_generation("breakfast")

    assert isinstance(draft, ScenarioDraft)
    assert call_count["n"] == 2, "filter should have been called twice"
    assert len(broaden_counter) == 1, "broaden_queries should fire once on retry"


@pytest.mark.asyncio
async def test_retries_on_assembly_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """First assembly call raises; next-best OCR succeeds on retry."""
    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(3)])
    _patch_download_all_succeed(monkeypatch)
    _patch_filter(monkeypatch, lambda img: True)

    # Two distinct OCR results so the orchestrator has a second to try.
    ocr_a = _ocr("img0", raw="A" * 100, confidence=0.95)  # higher score, tried first
    ocr_b = _ocr("img1", raw="B" * 50, confidence=0.80)

    async def fake_ocr(img, *, settings=None):
        if img.original.title == "img0":
            return ocr_a
        if img.original.title == "img1":
            return ocr_b
        return _ocr(img.original.title, confidence=0.5)

    monkeypatch.setattr(orchestrator.vision, "extract_text", fake_ocr)

    call_count = {"n": 0}

    async def fake_assembly(ocr):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise AssemblyError("first attempt failed")
        return _draft(ocr.image, raw=ocr.raw_text)

    captured = _patch_assembly(monkeypatch, fake_assembly)

    draft = await run_generation("anything")

    assert isinstance(draft, ScenarioDraft)
    assert call_count["n"] == 2, "assembly should have been retried once"
    # The retry should walk the OCR results in best->worst order.
    assert captured[0] is ocr_a
    assert captured[1] is ocr_b


@pytest.mark.asyncio
async def test_fails_after_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filter never returns enough keepers -> GenerationFailed(stage='filter')."""
    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    _patch_broaden(monkeypatch, ["broad1", "broad2", "broad3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(3)])
    _patch_download_all_succeed(monkeypatch)
    _patch_filter(monkeypatch, lambda img: False)  # always reject

    with pytest.raises(GenerationFailed) as excinfo:
        await run_generation("anything")
    assert excinfo.value.stage == "filter"


@pytest.mark.asyncio
async def test_progress_callback_called_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage names arrive in the canonical order from DESIGN.md Section 7."""
    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(3)])
    _patch_download_all_succeed(monkeypatch)
    _patch_filter(monkeypatch, lambda img: True)

    async def fake_ocr(img, *, settings=None):
        return _ocr(img.original.title)

    monkeypatch.setattr(orchestrator.vision, "extract_text", fake_ocr)

    async def fake_assembly(ocr):
        return _draft(ocr.image)

    _patch_assembly(monkeypatch, fake_assembly)

    received: list[tuple[str, dict]] = []

    async def on_progress(stage, detail):
        received.append((stage, detail))

    await run_generation("anything", on_progress=on_progress)

    assert [s for s, _ in received] == [
        "queries_generated",
        "images_searched",
        "images_downloaded",
        "images_filtered",
        "ocr_in_progress",
        "assembling",
        "done",
    ]
    # queries_generated carries the queries; images_filtered carries kept count
    assert received[0][1]["queries"] == ["q1", "q2", "q3"]
    assert received[3][1]["kept"] >= 2


@pytest.mark.asyncio
async def test_total_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Total wall-clock budget aborts a stuck OCR call.

    To keep the suite fast we shrink the budget to 0.2 s and have OCR
    sleep 5 s -- the orchestrator should fail with stage="timeout"
    in well under a second.
    """
    monkeypatch.setattr(orchestrator, "TOTAL_BUDGET_S", 0.2)

    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(3)])
    _patch_download_all_succeed(monkeypatch)
    _patch_filter(monkeypatch, lambda img: True)
    _patch_ocr(monkeypatch, _ocr("slow"), delay_s=5.0)

    start = asyncio.get_event_loop().time()
    with pytest.raises(GenerationFailed) as excinfo:
        await run_generation("anything")
    elapsed = asyncio.get_event_loop().time() - start

    assert excinfo.value.stage == "timeout"
    assert elapsed < 1.0, f"timeout took {elapsed:.2f}s, expected < 1.0s"


@pytest.mark.asyncio
async def test_ocr_failure_surfaces_first_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When every OCR call fails, the first error reaches the user.

    Regression test: the orchestrator used to swallow each per-image
    OcrError silently and surface only "no OCR result succeeded on
    any kept image" -- giving zero diagnostic info. Now it logs
    every failure at WARNING level (with the image URL) and includes
    the first error's detail in the GenerationFailed message.
    """
    _patch_queries(monkeypatch, ["q1", "q2", "q3"])
    _patch_search(monkeypatch, [_image_result(f"img{i}") for i in range(3)])
    _patch_download_all_succeed(monkeypatch)
    _patch_filter(monkeypatch, lambda img: True)

    call_index = {"n": 0}

    async def fake_ocr(img, *, settings=None):
        i = call_index["n"]
        call_index["n"] += 1
        # Different errors per image so we can verify "first" wins.
        raise OcrError(f"safety block on image #{i}")

    monkeypatch.setattr(orchestrator.vision, "extract_text", fake_ocr)

    with caplog.at_level(logging.WARNING, logger="app.agent.orchestrator"):
        with pytest.raises(GenerationFailed) as excinfo:
            await run_generation("anything")

    assert excinfo.value.stage == "ocr"
    # Detail must include the count and the *first* error's message.
    assert "OCR attempt(s) failed" in excinfo.value.detail
    assert "first error: safety block on image #0" in excinfo.value.detail

    # And every per-image failure should have been logged with its URL.
    ocr_warnings = [r for r in caplog.records if "OCR failed for" in r.message]
    assert len(ocr_warnings) == 3
    assert any("img0.jpg" in r.message for r in ocr_warnings)


# Silence noise: unused import in some test branches due to the monkey-patched
# helpers pulling json/asyncio for shape in other branches.
_ = json
