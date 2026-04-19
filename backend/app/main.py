"""FastAPI application factory + module-level ``app`` instance.

Owns:

* ASGI app construction (title, openapi metadata)
* CORS middleware (origins from settings)
* Health check at ``GET /healthz``
* Router registration: scenarios, jobs, tasks, history, images

See DESIGN.md Section 4 + Section 6.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import history, images, jobs, scenarios, tasks
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build a fresh FastAPI app with middleware + routes wired up.

    Defined as a factory so tests can construct independent instances
    (or import the module-level ``app`` for the production path).
    """
    settings = get_settings()

    application = FastAPI(
        title="Scenarios App API",
        description=(
            "Generates authentic real-world Chinese reading scenarios on demand. "
            "Composes with the Pinyin Tool extension via plain DOM."
        ),
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, Any]:
        """Trivial liveness probe used by tests and orchestration.

        Returns ``{"status": "ok"}`` on success.
        """
        return {"status": "ok"}

    application.include_router(scenarios.router)
    application.include_router(jobs.router)
    application.include_router(tasks.router)
    application.include_router(history.router)
    application.include_router(images.router)

    return application


app = create_app()
