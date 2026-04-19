"""Unit tests for ``app.agent.search.search_images``.

Strategy: monkeypatch the synchronous helper
``app.agent.search._ddg_search_sync`` so the tests neither spin up a
thread pool nor touch the network. The recorded fixture in
``tests/fixtures/api_responses/ddg_images_breakfast_beijing.json``
is the canonical input for the happy-path test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent import search as search_mod
from app.agent.search import SearchError, search_images
from app.agent.types import ImageResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "api_responses"


def _load_fixture(name: str) -> list[dict]:
    """Load and parse a JSON fixture from ``tests/fixtures/api_responses``."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _patch_ddg(monkeypatch: pytest.MonkeyPatch, return_value: list[dict]) -> None:
    """Replace the sync DDG helper with a constant-returning fake."""

    def fake(_query: str, _max_results: int) -> list[dict]:
        return list(return_value)

    monkeypatch.setattr(search_mod, "_ddg_search_sync", fake)


@pytest.mark.asyncio
async def test_parses_ddg_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded DDG fixture parses to 10 :class:`ImageResult` objects."""
    fixture = _load_fixture("ddg_images_breakfast_beijing.json")
    _patch_ddg(monkeypatch, fixture)

    results = await search_images("北京 早餐 实拍 菜单", limit=10)

    assert len(results) == 10
    first = results[0]
    assert isinstance(first, ImageResult)
    assert first.url == "https://img.dianping.com/menu/old-beijing-breakfast-1.jpg"
    assert first.title == "北京老字号早餐店菜单实拍"
    # DDG calls the source-page link `url`; we surface it as
    # source_page_url (its `image` field is the direct image URL).
    assert first.source_page_url == "https://www.dianping.com/shop/G1A1A1A1"
    assert first.width == 1200
    assert first.height == 1600


@pytest.mark.asyncio
async def test_filters_data_uri_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``data:`` URL in the response is skipped, not parsed."""
    payload = [
        {
            "title": "real",
            "image": "https://example.com/photo.jpg",
            "url": "https://example.com/page",
            "width": 800,
            "height": 600,
        },
        {
            "title": "data uri placeholder",
            "image": "data:image/png;base64,iVBORw0KGgo=",
            "url": "https://example.com/data-page",
            "width": 1,
            "height": 1,
        },
    ]
    _patch_ddg(monkeypatch, payload)

    results = await search_images("anything", limit=10)

    assert len(results) == 1
    assert results[0].url == "https://example.com/photo.jpg"


@pytest.mark.asyncio
async def test_dedupes_by_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Identical image URLs across DDG result pages collapse to one entry.

    DDG occasionally returns the same image twice when paginating;
    deduping at the search stage keeps downstream OCR from doing
    duplicate work on the same bytes.
    """
    payload = [
        {"title": "a", "image": "https://example.com/a.jpg", "url": "https://a.com"},
        {"title": "b", "image": "https://example.com/b.jpg", "url": "https://b.com"},
        {"title": "a-dup", "image": "https://example.com/a.jpg", "url": "https://a.com"},
        {"title": "c", "image": "https://example.com/c.jpg", "url": "https://c.com"},
    ]
    _patch_ddg(monkeypatch, payload)

    results = await search_images("anything", limit=10)

    assert [r.url for r in results] == [
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
        "https://example.com/c.jpg",
    ]


@pytest.mark.asyncio
async def test_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if DDG returns 30 results, requesting limit=5 returns 5."""
    payload = [
        {
            "title": f"item {i}",
            "image": f"https://example.com/{i}.jpg",
            "url": f"https://site{i}.com",
            "width": 100,
            "height": 100,
        }
        for i in range(1, 31)
    ]
    _patch_ddg(monkeypatch, payload)

    results = await search_images("anything", limit=5)

    assert len(results) == 5
    assert [r.url for r in results] == [
        f"https://example.com/{i}.jpg" for i in range(1, 6)
    ]


@pytest.mark.asyncio
async def test_raises_on_ddg_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DDG-side exception (rate limit, network, etc.) becomes :class:`SearchError`.

    The original exception is chained via ``raise ... from`` so the
    cause survives in tracebacks; we assert on the wrapper message
    here so callers can rely on the type without knowing about
    ``ddgs``-specific exception classes.
    """

    def boom(_query: str, _max_results: int) -> list[dict]:
        raise RuntimeError("rate limited")

    monkeypatch.setattr(search_mod, "_ddg_search_sync", boom)

    with pytest.raises(SearchError) as excinfo:
        await search_images("anything")

    assert excinfo.value.status_code is None  # DDG has no HTTP status
    assert "rate limited" in excinfo.value.detail
