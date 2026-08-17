"""Read-only access to the immutable local action audit trail."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request

from jarvis.capabilities.memory import AuditRecord

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditRecord])
async def list_audit(
    request: Request, limit: int = Query(default=100, ge=1, le=500)
) -> list[AuditRecord]:
    """Return newest local audit events without exposing a mutation endpoint."""
    return await asyncio.to_thread(request.app.state.memory_store.list_audit, limit)
