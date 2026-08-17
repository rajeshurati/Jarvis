"""Durable workflow definition and inspection endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from jarvis.capabilities.memory import WorkflowRecord, WorkflowStepRecord

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    commands: list[str] = Field(min_length=1, max_length=20)


@router.get("", response_model=list[WorkflowRecord])
async def list_workflows(request: Request) -> list[WorkflowRecord]:
    return await asyncio.to_thread(request.app.state.memory_store.list_workflows)


@router.post("", response_model=WorkflowRecord, status_code=status.HTTP_201_CREATED)
async def create_workflow(request: Request, item: WorkflowInput) -> WorkflowRecord:
    try:
        return await asyncio.to_thread(
            request.app.state.memory_store.create_workflow, item.name, item.commands
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{workflow_id}/steps", response_model=list[WorkflowStepRecord])
async def list_workflow_steps(
    request: Request, workflow_id: int
) -> list[WorkflowStepRecord]:
    if await asyncio.to_thread(request.app.state.memory_store.get_workflow, workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await asyncio.to_thread(
        request.app.state.memory_store.list_workflow_steps, workflow_id
    )
