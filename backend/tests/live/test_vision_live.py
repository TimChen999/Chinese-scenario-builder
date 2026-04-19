"""Live OCR tests against the real Gemini Pro vision endpoint.

Gated by ``RUN_LIVE_TESTS=1`` because every run costs Gemini tokens.
Each test loads a hand-curated photo from ``tests/fixtures/images/``,
runs OCR against the real API, then asserts character-level Jaccard
similarity vs. the matching ``_expected.json`` is at least 0.85.

Jaccard is a coarse but stable measure: it tolerates minor OCR
disagreements (a missed punctuation mark, a swapped character) while
catching gross failures (the model hallucinates a totally different
text).

If the placeholder fixtures have not been replaced with real photos,
these tests will rightly fail -- they are part of the Definition of
Done for Step 3, not part of the unit suite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.agent.types import DownloadedImage, ImageResult
from app.agent.vision import extract_text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"),
    reason="Set RUN_LIVE_TESTS=1 to opt into live external-service tests.",
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"


def _char_jaccard(a: str, b: str) -> float:
    """Character-level Jaccard similarity in [0, 1]; 1.0 for two empties."""
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _load_image(name: str) -> DownloadedImage:
    """Load a fixture photo into a :class:`DownloadedImage`."""
    path = FIXTURE_DIR / name
    payload = path.read_bytes()
    if not payload:
        pytest.skip(
            f"{name} is an empty placeholder; replace it with a real photo to run this test."
        )
    return DownloadedImage(
        bytes_=payload,
        mime="image/jpeg",
        original=ImageResult(url=f"file://{path}", title=name),
    )


def _load_expected(name: str) -> dict:
    """Load the matching ``_expected.json`` next to a fixture image."""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


async def _run_one(image_name: str, expected_name: str) -> None:
    """Drive one OCR call + Jaccard assertion. Prints output for review."""
    image = _load_image(image_name)
    expected = _load_expected(expected_name)

    result = await extract_text(image)
    similarity = _char_jaccard(result.raw_text, expected["raw_text"])

    print(f"\n--- {image_name} ---")
    print(f"OCR result ({result.confidence:.2f}):\n{result.raw_text}")
    print(f"Expected:\n{expected['raw_text']}")
    print(f"Jaccard similarity: {similarity:.3f}")

    assert similarity >= 0.85, (
        f"{image_name}: similarity {similarity:.3f} < 0.85"
    )


@pytest.mark.asyncio
async def test_menu_001() -> None:
    """OCR the menu fixture and compare to the expected text."""
    await _run_one("menu_001.jpg", "menu_001_expected.json")


@pytest.mark.asyncio
async def test_sign_001() -> None:
    """OCR the sign fixture and compare to the expected text."""
    await _run_one("sign_001.jpg", "sign_001_expected.json")


@pytest.mark.asyncio
async def test_notice_001() -> None:
    """OCR the notice fixture and compare to the expected text."""
    await _run_one("notice_001.jpg", "notice_001_expected.json")
