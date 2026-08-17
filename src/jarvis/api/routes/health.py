"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis import __version__
from jarvis.core.config import Settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Public health status without sensitive configuration."""

    status: str
    version: str
    environment: str
    local_only: bool


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report liveness and the privacy posture."""
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.environment,
        local_only=not settings.allow_network,
    )
