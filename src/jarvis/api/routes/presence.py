"""Local room-presence monitoring endpoints."""

from __future__ import annotations

import asyncio
from typing import cast

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from jarvis.application.presence_service import PresenceMonitorService
from jarvis.capabilities.memory import PresenceEventRecord

router = APIRouter(prefix="/presence", tags=["presence"])


class PresenceStatus(BaseModel):
    enabled: bool
    last_error: str | None


def _service(request: Request) -> PresenceMonitorService:
    return cast(PresenceMonitorService, request.app.state.presence_service)


@router.get("/status", response_model=PresenceStatus)
async def status(request: Request) -> PresenceStatus:
    service = _service(request)
    return PresenceStatus(enabled=service.enabled, last_error=service.last_error)


@router.get("/events", response_model=list[PresenceEventRecord])
async def events(
    request: Request, limit: int = Query(default=50, ge=1, le=500)
) -> list[PresenceEventRecord]:
    return await asyncio.to_thread(request.app.state.memory_store.list_presence_events, limit)


@router.post("/enable", response_model=PresenceStatus)
async def enable(request: Request) -> PresenceStatus:
    service = _service(request)
    service.enable()
    return PresenceStatus(enabled=True, last_error=service.last_error)


@router.post("/disable", response_model=PresenceStatus)
async def disable(request: Request) -> PresenceStatus:
    service = _service(request)
    service.disable()
    request.app.state.camera_snapshot_store.clear()
    return PresenceStatus(enabled=False, last_error=service.last_error)
