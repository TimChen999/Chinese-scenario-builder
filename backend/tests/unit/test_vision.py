"""Unit tests for ``app.agent.vision.extract_text``.

Strategy: monkeypatch ``app.agent.vision._gemini.generate_text`` so
the tests never touch the real Gemini SDK. The resize test exercises
``_resize_if_needed`` directly with a programmatically generated
image (avoids depending on a real fixture).
"""

from __future__ import annotations

import json
import os
from io import BytesIO

import pytest
from PIL import Image

from app.agent import vision
from app.agent.types import DownloadedImage, ImageResult
from app.agent.vision import (
    MAX_INLINE_BYTES,
    MAX_LONGEST_SIDE_PX,
    OcrError,
    _resize_if_needed,
    extract_text,
)


def _make_image(payload: bytes, mime: str = "image/jpeg") -> DownloadedImage:
    """Wrap raw bytes in the DownloadedImage shape the OCR module expects."""
    return DownloadedImage(
        bytes_=payload,
        mime=mime,
        original=ImageResult(url="https://example.com/x.jpg", title="x"),
    )


def _patch_generate_text(monkeypatch: pytest.MonkeyPatch, return_value: str) -> dict:
    """Replace ``vision._gemini.generate_text`` with a recording fake.

    Returns a dict that the test can inspect after ``extract_text``
    runs, exposing the actual ``contents`` argument the SUT built.
    """
    captured: dict = {}

    async def fake_generate_text(**kwargs):
        captured.update(kwargs)
        return return_value

    monkeypatch.setattr(vision._gemini, "generate_text", fake_generate_text)
    return captured


@pytest.mark.asyncio
async def test_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """A well-formed JSON response is mapped onto :class:`OcrResult`."""
    canned = json.dumps(
        {
            "raw_text": "豆浆 3元\n油条 2元",
            "confidence": 0.94,
            "scene_type": "menu",
            "notes": "handwritten",
        }
    )
    _patch_generate_text(monkeypatch, canned)

    image = _make_image(b"fake-jpeg-bytes")
    result = await extract_text(image)

    assert result.raw_text == "豆浆 3元\n油条 2元"
    assert result.confidence == pytest.approx(0.94)
    assert result.scene_type_guess == "menu"
    assert result.notes == "handwritten"
    # The DownloadedImage we supplied is preserved (no resize needed
    # because it's tiny).
    assert result.image is image


@pytest.mark.asyncio
async def test_resizes_oversize_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """Images > 4 MB are resized to <= 4 MB / longest-side <= 1568 px.

    Verifies via ``_resize_if_needed`` directly (deterministic) and via
    ``extract_text``'s outgoing payload (end-to-end).
    """
    # Random bytes defeat JPEG / PNG compression so the encoded blob
    # is comfortably > 4 MB. PNG is uncompressed enough to guarantee
    # that even without random data tricks; we use random to be sure.
    pixels = os.urandom(2200 * 2200 * 3)
    pil = Image.frombytes("RGB", (2200, 2200), pixels)
    buf = BytesIO()
    pil.save(buf, format="PNG")
    big_bytes = buf.getvalue()
    assert len(big_bytes) > MAX_INLINE_BYTES, "test setup: random PNG should exceed 4 MB"

    big_image = _make_image(big_bytes, mime="image/png")

    # Direct resize check
    resized = _resize_if_needed(big_image)
    assert resized is not big_image
    assert len(resized.bytes_) < MAX_INLINE_BYTES
    pil_resized = Image.open(BytesIO(resized.bytes_))
    assert max(pil_resized.size) <= MAX_LONGEST_SIDE_PX
    assert pil_resized.size[0] == pil_resized.size[1], "aspect ratio preserved"
    assert resized.mime == "image/jpeg"

    # End-to-end check: the bytes passed to Gemini are the resized ones.
    captured = _patch_generate_text(
        monkeypatch,
        json.dumps(
            {"raw_text": "x", "confidence": 0.5, "scene_type": "other", "notes": None}
        ),
    )
    await extract_text(big_image)
    contents = captured["contents"]
    image_part = next(c for c in contents if hasattr(c, "inline_data") or hasattr(c, "_raw_bytes"))
    # google-genai's Part stores inline_data.data; use a tolerant accessor.
    raw = getattr(getattr(image_part, "inline_data", None), "data", None)
    assert raw is not None, "image bytes should travel through inline_data"
    assert len(raw) < MAX_INLINE_BYTES


@pytest.mark.asyncio
async def test_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON output from Gemini surfaces as :class:`OcrError`."""
    _patch_generate_text(monkeypatch, "this is not JSON at all")

    image = _make_image(b"x")
    with pytest.raises(OcrError) as excinfo:
        await extract_text(image)
    assert "valid JSON" in excinfo.value.detail


@pytest.mark.asyncio
async def test_raises_on_schema_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Output missing a required field surfaces as :class:`OcrError`."""
    # Missing "scene_type" entirely.
    bad = json.dumps({"raw_text": "abc", "confidence": 0.5, "notes": None})
    _patch_generate_text(monkeypatch, bad)

    image = _make_image(b"x")
    with pytest.raises(OcrError) as excinfo:
        await extract_text(image)
    assert "schema" in excinfo.value.detail


@pytest.mark.asyncio
async def test_preserves_newlines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Newlines in ``raw_text`` survive the parse step verbatim."""
    canned = json.dumps(
        {
            "raw_text": "line1\nline2\nline3",
            "confidence": 0.8,
            "scene_type": "menu",
            "notes": None,
        }
    )
    _patch_generate_text(monkeypatch, canned)

    image = _make_image(b"x")
    result = await extract_text(image)
    assert result.raw_text == "line1\nline2\nline3"
    assert result.raw_text.count("\n") == 2
