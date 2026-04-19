"""Image search stage: query DuckDuckGo Images via the ``ddgs`` package.

This is the first stage of the agent pipeline (DESIGN.md Section 7).
Three queries -- one specific, one general, one with regional flavor
-- are produced upstream by the search-query LLM call; this module
just turns each query string into a list of candidate image URLs.

Diverges from DESIGN.md Section 3, which originally specified
SerpAPI (Google Images). DuckDuckGo was chosen instead so the app
ships with one secret instead of two: the same Google Gemini API key
that powers the Pinyin Tool extension is now the *only* required
credential. The pipeline's downstream stages are completely unaware
of this swap because the public function signature + ``SearchError``
exception type are unchanged.

Implementation notes:

* The ``ddgs`` library is synchronous, so we offload the call into a
  thread pool via :func:`asyncio.to_thread` to keep this module's
  async contract intact for the orchestrator.
* DDG occasionally returns the same image URL twice across pages;
  we dedupe by ``url`` here so downstream stages do not waste an
  OCR call on a duplicate.
* DDG can rate-limit / 403 on rapid successive calls; every failure
  mode is wrapped as :class:`SearchError` so callers do not need to
  import ``ddgs``-specific exception types.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ddgs import DDGS

from app.agent.types import ImageResult
from app.core.config import Settings

# Per-call timeout enforced by ``asyncio.wait_for`` over the threaded
# call. ``ddgs`` itself has its own internal HTTP timeouts but they
# are not always respected for the underlying captcha redirect path.
DEFAULT_TIMEOUT_S = 15.0

# Over-fetch factor: we ask DDG for ``limit * OVERFETCH`` results and
# then prune data: URIs / duplicates client-side. Two is enough in
# practice; raising it costs DDG quota for diminishing returns.
OVERFETCH = 2


class SearchError(Exception):
    """Raised on any failure to fetch or parse an image-search response.

    ``status_code`` is kept on the type for future search backends
    (e.g. Google CSE) that surface HTTP statuses; for the DuckDuckGo
    backend it is always ``None`` because ``ddgs`` does not expose
    one in its exception types.
    """

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _ddg_search_sync(query: str, max_results: int) -> list[dict[str, Any]]:
    """Synchronous DDG image-search call.

    Extracted into its own helper so unit tests can monkeypatch it
    without spinning up a thread pool. Returns the raw list of dicts
    that ``ddgs`` produces -- caller does the field mapping +
    pruning.
    """
    with DDGS() as client:
        # ``ddgs.images`` returns an iterator; we materialise it
        # inside the helper so the caller can ``len()`` the result
        # and so any iteration error surfaces here, not deeper in
        # the pipeline.
        return list(client.images(query, max_results=max_results))


async def search_images(
    query: str,
    *,
    limit: int = 10,
    settings: Settings | None = None,
) -> list[ImageResult]:
    """Search DuckDuckGo Images and return up to ``limit`` parsed results.

    Parameters
    ----------
    query
        The search string (Chinese or English). Passed verbatim to
        ``ddgs``.
    limit
        Maximum number of :class:`ImageResult` to return. Defends
        against DDG returning extra results: even if the response
        has more, we slice to ``limit`` after deduping.
    settings
        Currently unused (no API key needed). Kept on the signature
        for symmetry with the rest of the agent layer and for future
        backends that may need it.

    Raises
    ------
    SearchError
        On any DDG failure (rate limit, captcha, HTML format change,
        network error). The original exception is chained via
        ``raise ... from exc`` so the cause survives in tracebacks.

    Notes
    -----
    Filters two kinds of result up front: those without an ``image``
    URL, and those whose URL is a ``data:`` URI (we cannot download
    those, and they are usually small placeholders rather than real
    photos). Deduplicates by URL so identical images appearing across
    DDG result pages do not waste downstream OCR calls.
    """
    # ``settings`` accepted but not used -- keeps the signature
    # uniform with vision / filter / assembly which all take it.
    _ = settings

    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_ddg_search_sync, query, limit * OVERFETCH),
            timeout=DEFAULT_TIMEOUT_S,
        )
    except TimeoutError as exc:
        raise SearchError(
            f"DuckDuckGo image search exceeded {DEFAULT_TIMEOUT_S}s"
        ) from exc
    except Exception as exc:  # noqa: BLE001 -- ddgs raises a variety of types
        raise SearchError(
            f"DuckDuckGo image search failed: {type(exc).__name__}: {exc}"
        ) from exc

    parsed: list[ImageResult] = []
    seen: set[str] = set()
    for item in raw:
        # DDG response shape: {"title", "image", "thumbnail", "url",
        # "height", "width", "source"}. We map ``image`` -> our
        # canonical direct-image ``url``, and DDG's ``url`` (the
        # source page link) -> our ``source_page_url``.
        url = item.get("image")
        if not url or url.startswith("data:") or url in seen:
            continue
        seen.add(url)
        parsed.append(
            ImageResult(
                url=url,
                title=item.get("title"),
                source_page_url=item.get("url"),
                width=item.get("width"),
                height=item.get("height"),
            )
        )
        if len(parsed) >= limit:
            break

    return parsed
