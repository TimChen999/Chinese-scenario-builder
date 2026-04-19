"""On-disk image storage + URL download helpers.

Owns three responsibilities, kept in one module because they are all
"the bytes of an image moving across a boundary":

* :func:`download_image` -- pull an image from the open web into memory.
* :func:`save_image`     -- write a successful generation's source
                             image to disk, keyed by scenario id.
* :func:`image_path_for` -- look up the path for a previously saved image.

DESIGN.md Section 4 lists this module in ``app/services/``; Step 7
of the build plan grows it to include save/load for the API layer.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx

from app.agent.types import DownloadedImage, ImageResult
from app.core.config import Settings, get_settings

# ─── Defaults ──────────────────────────────────────────────────────
DEFAULT_DOWNLOAD_TIMEOUT_S = 8.0
# 12 MB is generous; anything bigger is almost certainly a high-res
# desktop wallpaper, not a useful menu / sign photo.
DEFAULT_MAX_BYTES = 12 * 1024 * 1024


class ImageDownloadError(Exception):
    """Raised when downloading a candidate image fails."""

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


# ─── Download ──────────────────────────────────────────────────────


async def download_image(
    image: ImageResult,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_s: float = DEFAULT_DOWNLOAD_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> DownloadedImage:
    """Fetch the bytes of an :class:`ImageResult` over HTTP.

    Parameters
    ----------
    image
        The candidate to download; ``image.url`` must be a fetchable
        URL (``data:`` URIs are filtered out by the search stage).
    client
        Optional pre-built ``httpx.AsyncClient`` for connection pooling.
    timeout_s
        Per-request timeout (DESIGN.md Section 7: 8 s default).
    max_bytes
        Hard cap on response size; anything bigger raises rather than
        loading multi-MB blobs into memory.

    Raises
    ------
    ImageDownloadError
        On HTTP failure, non-200 response, or oversized payload.
    """
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=timeout_s,
            follow_redirects=True,
            # Be a polite, identifiable client; some sites block default UAs.
            headers={"User-Agent": "ScenariosAppBot/0.1 (+https://example.local)"},
        )
    try:
        try:
            response = await client.get(image.url)
        except httpx.HTTPError as exc:
            raise ImageDownloadError(f"Image download failed: {exc}") from exc
    finally:
        if own_client:
            await client.aclose()

    if response.status_code != 200:
        raise ImageDownloadError(
            f"Image returned {response.status_code}", status_code=response.status_code
        )

    content_length = int(response.headers.get("content-length", 0))
    if content_length and content_length > max_bytes:
        raise ImageDownloadError(
            f"Image too large: content-length {content_length} > {max_bytes}"
        )
    if len(response.content) > max_bytes:
        raise ImageDownloadError(
            f"Image too large: body {len(response.content)} > {max_bytes}"
        )

    mime = (response.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
    return DownloadedImage(bytes_=response.content, mime=mime, original=image)


# ─── On-disk persistence (used by Step 7) ──────────────────────────


def _ext_for(mime: str) -> str:
    """Return a safe file extension for a MIME type, defaulting to ``.bin``."""
    ext = mimetypes.guess_extension(mime) or ""
    if not ext:
        # mimetypes occasionally returns None for image/jpeg on some
        # platforms; force a sensible fallback for the common case.
        if mime == "image/jpeg":
            return ".jpg"
        if mime == "image/png":
            return ".png"
        if mime == "image/webp":
            return ".webp"
        return ".bin"
    # mimetypes returns ".jpe" for image/jpeg on Windows; normalize.
    return ".jpg" if ext == ".jpe" else ext


def save_image(
    scenario_id: str, image: DownloadedImage, *, settings: Settings | None = None
) -> Path:
    """Write ``image`` to ``IMAGE_STORAGE_DIR/{scenario_id}{ext}``.

    Returns the relative-style path string suitable for storing in
    the Scenario row's ``source_image_path`` column.
    """
    if settings is None:
        settings = get_settings()
    storage = settings.image_storage_path
    storage.mkdir(parents=True, exist_ok=True)
    target = storage / f"{scenario_id}{_ext_for(image.mime)}"
    target.write_bytes(image.bytes_)
    return target


def image_path_for(
    scenario_id: str,
    *,
    image_path_hint: str | None = None,
    settings: Settings | None = None,
) -> Path | None:
    """Locate a previously saved image for ``scenario_id``.

    If the Scenario row already records a path we trust it; otherwise
    we fall back to scanning ``IMAGE_STORAGE_DIR`` for any file whose
    stem matches the scenario id.
    """
    if image_path_hint:
        path = Path(image_path_hint)
        if path.is_file():
            return path
    if settings is None:
        settings = get_settings()
    storage = settings.image_storage_path
    if not storage.is_dir():
        return None
    for candidate in storage.glob(f"{scenario_id}.*"):
        if candidate.is_file():
            return candidate
    return None
