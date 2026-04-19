"""Smoke tests for the bare FastAPI app: liveness probe + CORS preflight.

DESIGN.md Step 1 lists these as the two integration tests required
before declaring the skeleton done.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient) -> None:
    """``GET /healthz`` returns 200 with the canonical body."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_cors_preflight(client: AsyncClient) -> None:
    """An OPTIONS preflight from the configured origin is allowed.

    Asserts that:
      * the response status is 200
      * ``Access-Control-Allow-Origin`` echoes the request origin
      * the requested method is in ``Access-Control-Allow-Methods``
    """
    response = await client.options(
        "/healthz",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods or "*" in allow_methods
