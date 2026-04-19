"""Live test for the SerpAPI image-search call.

Gated by the ``RUN_LIVE_TESTS`` env var because it costs money and
requires a real ``SERPAPI_KEY``. Off by default; opt in with
``RUN_LIVE_TESTS=1 pytest tests/live/test_search_live.py``.
"""

from __future__ import annotations

import os

import pytest

from app.agent.search import search_images

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"),
    reason="Set RUN_LIVE_TESTS=1 to opt into live external-service tests.",
)


@pytest.mark.asyncio
async def test_real_query() -> None:
    """A live SerpAPI query for a real Beijing breakfast prompt returns results.

    Asserts at least 5 results so the rest of the agent pipeline has
    something to work with. Prints the first three for manual review
    -- live tests are alerts, not regressions, so seeing the actual
    response helps when SerpAPI's results drift.
    """
    results = await search_images("北京 早餐 实拍 菜单", limit=10)
    assert len(results) >= 5, f"expected at least 5 results, got {len(results)}"
    for r in results[:3]:
        print(r)
