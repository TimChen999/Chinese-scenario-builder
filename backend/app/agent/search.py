"""Image search stage: query SerpAPI's google_images engine.

This is the first stage of the agent pipeline (DESIGN.md Section 7).
Three queries -- one specific, one general, one with regional flavor
-- are produced upstream by the search-query LLM call; this module
just turns each query string into a list of candidate image URLs.

We deliberately keep the module pure-async + pure-functional: no
state, no side effects beyond the HTTP call. That makes it trivial
to mock in unit tests via pytest-httpx.
"""

from __future__ import annotations

import httpx

from app.agent.types import ImageResult
from app.core.config import Settings, get_settings

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
DEFAULT_TIMEOUT_S = 10.0


class SearchError(Exception):
    """Raised on any failure to fetch or parse a SerpAPI response.

    ``status_code`` is None when the failure was a configuration
    problem (missing key) or a network error before a response was
    received; otherwise it is the HTTP status from SerpAPI.
    """

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def search_images(
    query: str,
    *,
    limit: int = 10,
    client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> list[ImageResult]:
    """Search Google Images via SerpAPI and return up to ``limit`` parsed results.

    Parameters
    ----------
    query
        The search string (Chinese or English). Passed verbatim to
        SerpAPI's ``q`` parameter.
    limit
        Maximum number of :class:`ImageResult` to return. Defends
        against SerpAPI returning extra results: even if the response
        has more, we slice to ``limit``.
    client
        Optional pre-built ``httpx.AsyncClient`` -- pass one in to
        share connection pooling across calls. If ``None``, a new
        client is created and closed inside the function.
    settings
        Optional pre-built :class:`Settings`; defaults to the cached
        one from :func:`app.core.config.get_settings`.

    Raises
    ------
    SearchError
        If ``SERPAPI_KEY`` is not configured (no HTTP call is made),
        or if SerpAPI returns a non-200 response.

    Notes
    -----
    Filters two kinds of result up front: those without an
    ``original`` URL, and those whose ``original`` is a ``data:``
    URI (we cannot download those, and they are usually small
    SerpAPI-internal placeholders rather than real photos).
    """
    if settings is None:
        settings = get_settings()
    if not settings.SERPAPI_KEY:
        # Surface configuration problems without a network round trip
        # so the user sees the real cause immediately.
        raise SearchError("SERPAPI_KEY is not configured")

    params = {
        "engine": "google_images",
        "q": query,
        "api_key": settings.SERPAPI_KEY,
        "num": limit,
        "ijn": 0,
    }

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S)
    try:
        try:
            response = await client.get(SERPAPI_BASE_URL, params=params)
        except httpx.HTTPError as exc:
            raise SearchError(f"SerpAPI request failed: {exc}") from exc
    finally:
        if own_client:
            await client.aclose()

    if response.status_code != 200:
        raise SearchError(
            f"SerpAPI returned {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
        )

    data = response.json()
    raw_results = data.get("images_results", []) or []

    parsed: list[ImageResult] = []
    for item in raw_results:
        original = item.get("original")
        if not original or original.startswith("data:"):
            continue
        parsed.append(
            ImageResult(
                url=original,
                title=item.get("title"),
                source_page_url=item.get("source"),
                width=item.get("original_width"),
                height=item.get("original_height"),
            )
        )
        if len(parsed) >= limit:
            break

    return parsed
