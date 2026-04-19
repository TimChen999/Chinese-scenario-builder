"""Live test for the DuckDuckGo image-search call.

Gated by the ``RUN_LIVE_TESTS`` env var. Off by default; opt in with
``RUN_LIVE_TESTS=1 pytest tests/live/test_search_live.py``. DDG is
free + keyless, but live tests still hit the real internet so we
keep them off the default loop to keep CI hermetic.
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
    """A live DDG query for a real Beijing breakfast prompt returns results.

    Asserts at least 5 results so the rest of the agent pipeline has
    something to work with. Prints the first three for manual review
    -- live tests are alerts, not regressions, so seeing the actual
    response helps when DDG's results drift or its HTML layout changes.
    """
    results = await search_images("北京 早餐 实拍 菜单", limit=10)
    assert len(results) >= 5, f"expected at least 5 results, got {len(results)}"
    for r in results[:3]:
        print(r)
