"""Unit tests for ``app.agent.assembly``.

The recorded ``assembly_breakfast.json`` fixture is the canonical
"good" response. The other tests construct one-off payloads inline
to exercise specific failure modes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent import assembly as assembly_mod
from app.agent.assembly import AssemblyError, assemble
from app.agent.types import DownloadedImage, ImageResult, OcrResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "api_responses"


def _ocr_result(raw_text: str = "豆浆 3元\n油条 2元\n包子(肉) 4元\n包子(素) 3元") -> OcrResult:
    """Build an :class:`OcrResult` with realistic defaults for the assembly call."""
    image = DownloadedImage(
        bytes_=b"fake-jpeg",
        mime="image/jpeg",
        original=ImageResult(url="https://example.com/menu.jpg", title="menu"),
    )
    return OcrResult(
        image=image,
        raw_text=raw_text,
        confidence=0.92,
        scene_type_guess="menu",
        notes=None,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, return_text: str) -> None:
    """Replace the underlying Gemini call with a constant returning fake."""

    async def fake_generate_text(**_kwargs):
        return return_text

    monkeypatch.setattr(assembly_mod._gemini, "generate_text", fake_generate_text)


@pytest.mark.asyncio
async def test_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded fixture parses cleanly into a :class:`ScenarioDraft`."""
    fixture = (FIXTURES_DIR / "assembly_breakfast.json").read_text(encoding="utf-8")
    _patch(monkeypatch, fixture)

    ocr = _ocr_result()
    draft = await assemble(ocr, "ordering breakfast in Beijing", region="Beijing")

    assert draft.scene_type == "menu"
    assert "你刚走进" in draft.scene_setup
    assert len(draft.tasks) == 3
    first = draft.tasks[0]
    assert first.prompt.startswith("What is the cheapest")
    assert first.expected_answer == "油条"
    assert "油条" in first.acceptable_answers
    # Source image carries through unchanged.
    assert draft.source_image is ocr.image


@pytest.mark.asyncio
async def test_validates_scene_setup_has_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    """An English-only ``scene_setup`` is rejected by the validator."""
    bad = json.dumps(
        {
            "scene_setup": "You walk into a Beijing breakfast stall.",
            "tasks": [
                {
                    "prompt": "What is the cheapest item?",
                    "answer_type": "exact",
                    "expected_answer": "油条",
                    "acceptable_answers": ["油条"],
                    "explanation": "youtiao is 2 yuan",
                }
            ],
        }
    )
    _patch(monkeypatch, bad)

    with pytest.raises(AssemblyError) as excinfo:
        await assemble(_ocr_result(), "x")
    assert "schema" in excinfo.value.detail or "Chinese" in excinfo.value.detail


@pytest.mark.asyncio
async def test_validates_task_count_min(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty ``tasks`` list raises :class:`AssemblyError`."""
    bad = json.dumps({"scene_setup": "你刚走进早餐店。", "tasks": []})
    _patch(monkeypatch, bad)

    with pytest.raises(AssemblyError):
        await assemble(_ocr_result(), "x")


@pytest.mark.asyncio
async def test_validates_task_count_max(monkeypatch: pytest.MonkeyPatch) -> None:
    """Six tasks (1 over the cap) raises :class:`AssemblyError`."""
    six_tasks = [
        {
            "prompt": f"q{i}",
            "answer_type": "exact",
            "expected_answer": f"a{i}",
            "acceptable_answers": [f"a{i}"],
            "explanation": "x",
        }
        for i in range(6)
    ]
    bad = json.dumps({"scene_setup": "你刚走进早餐店。", "tasks": six_tasks})
    _patch(monkeypatch, bad)

    with pytest.raises(AssemblyError):
        await assemble(_ocr_result(), "x")


@pytest.mark.asyncio
async def test_acceptable_answers_includes_expected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If acceptable_answers omits expected_answer, it is auto-appended.

    Decision (plan, Step 5): be lenient. Adding the canonical answer
    to acceptable_answers cannot break correctness and avoids burning
    another expensive Pro call on a re-roll.
    """
    payload = json.dumps(
        {
            "scene_setup": "你刚走进早餐店。",
            "tasks": [
                {
                    "prompt": "Cheapest?",
                    "answer_type": "exact",
                    "expected_answer": "油条",
                    "acceptable_answers": ["youtiao"],  # missing 油条
                    "explanation": "x",
                }
            ],
        }
    )
    _patch(monkeypatch, payload)

    draft = await assemble(_ocr_result(), "x")
    task = draft.tasks[0]
    assert "油条" in task.acceptable_answers
    assert "youtiao" in task.acceptable_answers


@pytest.mark.asyncio
async def test_raw_content_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """``raw_content`` is byte-identical to ``ocr_result.raw_text``.

    This test is the most important one in the file. The authenticity
    invariant (DESIGN.md Section 1) is the entire point of the
    pipeline; if assembly ever silently rewrites the source text the
    app stops being authentic.

    To make the test sharp, the canned LLM response includes a
    *different* ``scene_setup`` than the input, and we feed an
    ``ocr_result`` whose ``raw_text`` has unusual whitespace,
    punctuation, and characters the LLM would be tempted to
    "normalise".
    """
    weird_raw = "豆浆\t  3元\n  油条 ¥2.00\n包子(肉)　4元"  # tabs, fullwidth space, nbsp-style chars
    ocr = _ocr_result(raw_text=weird_raw)

    payload = json.dumps(
        {
            "scene_setup": "你刚走进一家早餐店。",
            "tasks": [
                {
                    "prompt": "q",
                    "answer_type": "exact",
                    "expected_answer": "油条",
                    "acceptable_answers": ["油条"],
                    "explanation": "x",
                }
            ],
        }
    )
    _patch(monkeypatch, payload)

    draft = await assemble(ocr, "anything")
    assert draft.raw_content == weird_raw, "raw_content must NEVER be altered"
    # Belt + suspenders: byte equality.
    assert draft.raw_content.encode("utf-8") == weird_raw.encode("utf-8")
