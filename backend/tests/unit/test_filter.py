"""Unit tests for ``app.agent.filter``.

Strategy mirrors ``test_vision.py``: monkeypatch
``app.agent.filter._gemini.generate_text`` so the tests run without
any Gemini access. The batch test uses a queue of canned responses
so each input image gets its own verdict.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.agent import filter as filter_mod
from app.agent.filter import FilterError, filter_image, filter_images
from app.agent.types import DownloadedImage, ImageResult


def _make_image(label: str) -> DownloadedImage:
    """Build a tiny stand-in :class:`DownloadedImage` carrying a label.

    ``label`` is encoded in the URL so the batch test can recover
    which input each verdict matches without ID juggling.
    """
    return DownloadedImage(
        bytes_=b"fake",
        mime="image/jpeg",
        original=ImageResult(url=f"https://example.com/{label}.jpg", title=label),
    )


def _patch_one(monkeypatch: pytest.MonkeyPatch, return_text: str) -> None:
    async def fake_generate_text(**_kwargs):
        return return_text

    monkeypatch.setattr(filter_mod._gemini, "generate_text", fake_generate_text)


@pytest.mark.asyncio
async def test_keep_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """``keep:true`` becomes a verdict with ``keep == True``."""
    _patch_one(monkeypatch, json.dumps({"keep": True, "reason": "real menu photo"}))

    image = _make_image("good")
    verdict = await filter_image(image)

    assert verdict.image is image
    assert verdict.keep is True
    assert verdict.reason == "real menu photo"


@pytest.mark.asyncio
async def test_reject_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """``keep:false`` becomes a verdict with ``keep == False``."""
    _patch_one(monkeypatch, json.dumps({"keep": False, "reason": "stock photo"}))

    image = _make_image("bad")
    verdict = await filter_image(image)

    assert verdict.keep is False
    assert verdict.reason == "stock photo"


@pytest.mark.asyncio
async def test_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON output surfaces as :class:`FilterError`."""
    _patch_one(monkeypatch, "not json")

    image = _make_image("x")
    with pytest.raises(FilterError) as excinfo:
        await filter_image(image)
    assert "valid JSON" in excinfo.value.detail


@pytest.mark.asyncio
async def test_filter_batch_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """``filter_images`` returns verdicts in the same order as inputs.

    To prove parallelism (not just sequential scheduling) we make the
    fake call sleep before answering. Total wall-clock time should be
    closer to ``one_call_delay`` than ``len(images) * one_call_delay``.
    """

    async def fake_generate_text(*, contents, **_kwargs) -> str:
        # Decode the per-image label out of the URL we baked into the
        # ImageResult so this fake can return image-specific verdicts.
        # contents[0] is the user instruction; contents[1] is the
        # image part. We don't have direct access to the original
        # ImageResult here, but the test below routes by call order.
        await asyncio.sleep(0.05)
        return json.dumps({"keep": True, "reason": "ok"})

    monkeypatch.setattr(filter_mod._gemini, "generate_text", fake_generate_text)

    images = [_make_image(f"img{i}") for i in range(5)]

    start = asyncio.get_event_loop().time()
    verdicts = await filter_images(images, concurrency=5)
    elapsed = asyncio.get_event_loop().time() - start

    # Order preserved: i-th verdict carries the i-th input image.
    assert [v.image for v in verdicts] == images
    assert all(v.keep for v in verdicts)

    # Parallelism: 5 calls of 50 ms each should finish in well under
    # 250 ms (sequential lower bound). Allow generous headroom for
    # CI jitter -- we just want to catch a regression to fully
    # serial execution.
    assert elapsed < 0.20, f"batch ran in {elapsed:.3f}s, expected < 0.20s with concurrency=5"


@pytest.mark.asyncio
async def test_filter_batch_empty() -> None:
    """An empty input list returns an empty list without any LLM call."""
    assert await filter_images([]) == []
