"""Local interactive-webcam snapshot bridge."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/camera", tags=["camera"])


class CameraSnapshotStatus(BaseModel):
    available: bool
    age_seconds: float | None


@router.put("/snapshot", status_code=status.HTTP_204_NO_CONTENT)
async def update_camera_snapshot(request: Request) -> Response:
    """Accept one transient JPEG from the local interactive tray process."""
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="A JPEG camera snapshot is required")
    try:
        request.app.state.camera_snapshot_store.update(await request.body())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/snapshot/status", response_model=CameraSnapshotStatus)
async def camera_snapshot_status(request: Request) -> CameraSnapshotStatus:
    """Expose freshness metadata only, never webcam bytes."""
    available, age = request.app.state.camera_snapshot_store.status()
    return CameraSnapshotStatus(
        available=available,
        age_seconds=round(age, 3) if age is not None else None,
    )
