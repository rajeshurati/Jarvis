"""Local interactive-desktop snapshot bridge."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/screen", tags=["screen"])


class SnapshotStatus(BaseModel):
    available: bool
    age_seconds: float | None


@router.put("/snapshot", status_code=status.HTTP_204_NO_CONTENT)
async def update_snapshot(request: Request) -> Response:
    """Accept one transient PNG from the local interactive tray process."""
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/png":
        raise HTTPException(status_code=415, detail="A PNG screen snapshot is required")
    image = await request.body()
    try:
        left = int(request.headers.get("x-screen-left", "0"))
        top = int(request.headers.get("x-screen-top", "0"))
        request.app.state.screen_snapshot_store.update(image, left, top)
    except (ValueError, OverflowError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/snapshot/status", response_model=SnapshotStatus)
async def snapshot_status(request: Request) -> SnapshotStatus:
    """Expose freshness metadata only, never screenshot bytes."""
    available, age = request.app.state.screen_snapshot_store.status()
    return SnapshotStatus(
        available=available,
        age_seconds=round(age, 3) if age is not None else None,
    )
