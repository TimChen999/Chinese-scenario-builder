"""``GET /scenarios/{id}/image`` -- serve the cached source image file.

See DESIGN.md Section 6: ``Cache-Control: max-age=31536000, immutable``
because the image bytes for a given scenario id never change.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_settings_dep
from app.core.config import Settings
from app.db.models import Scenario
from app.services.image_store import image_path_for

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("/{scenario_id}/image", name="get_scenario_image")
async def serve_image(
    scenario_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> FileResponse:
    """Return the saved source image with an immutable cache header."""
    scenario = await session.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")

    path = image_path_for(
        scenario_id,
        image_path_hint=scenario.source_image_path,
        settings=settings,
    )
    if path is None:
        raise HTTPException(status_code=404, detail="image not available")

    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path=path,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "max-age=31536000, immutable"},
    )
