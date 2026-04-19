"""Unit tests for ``app.agent.search.search_images``.

All HTTP traffic is mocked via pytest-httpx so the tests are
deterministic and require no network. The recorded SerpAPI fixture
in ``tests/fixtures/api_responses/serpapi_breakfast_beijing.json``
is the canonical input for the happy-path test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from app.agent.search import SearchError, search_images
from app.agent.types import ImageResult
from app.core.config import Settings

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "api_responses"


def _test_settings(*, key: str = "test-serpapi-key") -> Settings:
    """Build a Settings instance with the SERPAPI_KEY override.

    Bypasses the env-file lookup so tests do not pick up secrets that
    happen to live on the developer's machine.
    """
    return Settings(SERPAPI_KEY=key, GEMINI_API_KEY="test-gemini-key")


def _load_fixture(name: str) -> dict:
    """Load and parse a JSON fixture from ``tests/fixtures/api_responses``."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_parses_serpapi_response(httpx_mock: HTTPXMock) -> None:
    """Recorded fixture parses to 10 :class:`ImageResult` objects."""
    fixture = _load_fixture("serpapi_breakfast_beijing.json")
    httpx_mock.add_response(json=fixture)

    results = await search_images(
        "北京 早餐 实拍 菜单", limit=10, settings=_test_settings()
    )

    assert len(results) == 10
    first = results[0]
    assert isinstance(first, ImageResult)
    assert first.url == "https://img.dianping.com/menu/old-beijing-breakfast-1.jpg"
    assert first.title == "北京老字号早餐店菜单实拍"
    assert first.source_page_url == "dianping.com"
    assert first.width == 1200
    assert first.height == 1600


@pytest.mark.asyncio
async def test_filters_data_uri_results(httpx_mock: HTTPXMock) -> None:
    """A ``data:`` URL in the response is skipped, not parsed."""
    payload = {
        "images_results": [
            {
                "position": 1,
                "title": "real",
                "source": "example.com",
                "original": "https://example.com/photo.jpg",
                "original_width": 800,
                "original_height": 600,
            },
            {
                "position": 2,
                "title": "data uri placeholder",
                "source": "data.example.com",
                "original": "data:image/png;base64,iVBORw0KGgo=",
                "original_width": 1,
                "original_height": 1,
            },
        ]
    }
    httpx_mock.add_response(json=payload)

    results = await search_images("anything", limit=10, settings=_test_settings())

    assert len(results) == 1
    assert results[0].url == "https://example.com/photo.jpg"


@pytest.mark.asyncio
async def test_respects_limit(httpx_mock: HTTPXMock) -> None:
    """Even if SerpAPI returns 30 results, requesting limit=5 returns 5."""
    payload = {
        "images_results": [
            {
                "position": i,
                "title": f"item {i}",
                "source": f"site{i}.com",
                "original": f"https://example.com/{i}.jpg",
                "original_width": 100,
                "original_height": 100,
            }
            for i in range(1, 31)
        ]
    }
    httpx_mock.add_response(json=payload)

    results = await search_images("anything", limit=5, settings=_test_settings())

    assert len(results) == 5
    assert [r.url for r in results] == [
        f"https://example.com/{i}.jpg" for i in range(1, 6)
    ]


@pytest.mark.asyncio
async def test_raises_on_500(httpx_mock: HTTPXMock) -> None:
    """A 500 response raises :class:`SearchError` carrying the status code."""
    httpx_mock.add_response(status_code=500, text="upstream blew up")

    with pytest.raises(SearchError) as excinfo:
        await search_images("anything", settings=_test_settings())

    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_raises_on_missing_api_key() -> None:
    """An empty ``SERPAPI_KEY`` raises before any HTTP call is attempted.

    No ``httpx_mock`` fixture is requested -- if the implementation
    accidentally tried to make a request, pytest-httpx would surface
    that as a "no response registered" error, indirectly catching the
    bug.
    """
    settings = _test_settings(key="")

    with pytest.raises(SearchError) as excinfo:
        await search_images("anything", settings=settings)

    assert excinfo.value.status_code is None
    assert "SERPAPI_KEY" in excinfo.value.detail
