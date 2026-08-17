"""Editable local-memory and project endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from jarvis.capabilities.memory import (
    MemoryRecord,
    ProjectNoteRecord,
    ProjectRecord,
    ProjectTaskRecord,
    ReminderRecord,
)

router = APIRouter(tags=["memory"])


class MemoryInput(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=2000)
    deadline: str | None = Field(default=None, max_length=40)


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=1000)


class TaskStatusInput(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|completed|cancelled)$")


class ProjectNoteInput(BaseModel):
    kind: str = Field(pattern="^(milestone|risk|dependency)$")
    content: str = Field(min_length=1, max_length=2000)


class ReminderInput(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    due_at: datetime


@router.get("/memory", response_model=list[MemoryRecord])
async def list_memory(request: Request, category: str | None = None) -> list[MemoryRecord]:
    return await asyncio.to_thread(request.app.state.memory_store.list_memories, category)


@router.put("/memory", response_model=MemoryRecord)
async def put_memory(request: Request, item: MemoryInput) -> MemoryRecord:
    return await asyncio.to_thread(
        request.app.state.memory_store.remember, item.category, item.key, item.value
    )


@router.get("/memory/search", response_model=list[MemoryRecord])
async def search_memory(request: Request, query: str, limit: int = 10) -> list[MemoryRecord]:
    """Search only the local SQLite memory store."""
    if not 1 <= len(query.strip()) <= 500 or not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Invalid memory search")
    return await asyncio.to_thread(
        request.app.state.memory_store.search_memories, query, limit
    )


@router.delete("/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(request: Request, memory_id: int) -> None:
    deleted = await asyncio.to_thread(request.app.state.memory_store.forget, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")


@router.get("/projects", response_model=list[ProjectRecord])
async def list_projects(request: Request) -> list[ProjectRecord]:
    return await asyncio.to_thread(request.app.state.memory_store.list_projects)


@router.post("/projects", response_model=ProjectRecord, status_code=status.HTTP_201_CREATED)
async def create_project(request: Request, item: ProjectInput) -> ProjectRecord:
    return await asyncio.to_thread(
        request.app.state.memory_store.create_project,
        item.name,
        item.objective,
        item.deadline,
    )


@router.post(
    "/projects/{project_id}/tasks",
    response_model=ProjectTaskRecord,
    status_code=status.HTTP_201_CREATED,
)
async def add_project_task(request: Request, project_id: int, item: TaskInput) -> ProjectTaskRecord:
    try:
        return await asyncio.to_thread(
            request.app.state.memory_store.add_project_task, project_id, item.title
        )
    except Exception as error:
        raise HTTPException(status_code=404, detail="Project not found") from error


@router.get("/projects/{project_id}/tasks", response_model=list[ProjectTaskRecord])
async def list_project_tasks(request: Request, project_id: int) -> list[ProjectTaskRecord]:
    return await asyncio.to_thread(request.app.state.memory_store.list_project_tasks, project_id)


@router.patch("/project-tasks/{task_id}", response_model=ProjectTaskRecord)
async def update_project_task(
    request: Request, task_id: int, item: TaskStatusInput
) -> ProjectTaskRecord:
    try:
        return await asyncio.to_thread(
            request.app.state.memory_store.update_project_task, task_id, item.status
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/projects/{project_id}/notes",
    response_model=ProjectNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
async def add_project_note(
    request: Request, project_id: int, item: ProjectNoteInput
) -> ProjectNoteRecord:
    try:
        return await asyncio.to_thread(
            request.app.state.memory_store.add_project_note,
            project_id,
            item.kind,
            item.content,
        )
    except Exception as error:
        raise HTTPException(status_code=404, detail="Project not found") from error


@router.get("/projects/{project_id}/notes", response_model=list[ProjectNoteRecord])
async def list_project_notes(request: Request, project_id: int) -> list[ProjectNoteRecord]:
    return await asyncio.to_thread(request.app.state.memory_store.list_project_notes, project_id)


@router.get("/reminders", response_model=list[ReminderRecord])
async def list_reminders(
    request: Request, include_delivered: bool = False
) -> list[ReminderRecord]:
    return await asyncio.to_thread(
        request.app.state.memory_store.list_reminders, include_delivered
    )


@router.post(
    "/reminders", response_model=ReminderRecord, status_code=status.HTTP_201_CREATED
)
async def create_reminder(request: Request, item: ReminderInput) -> ReminderRecord:
    if item.due_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="Reminder due_at must include a timezone")
    due_at = item.due_at.astimezone(UTC).isoformat(timespec="seconds")
    return await asyncio.to_thread(
        request.app.state.memory_store.create_reminder, item.title, due_at
    )


@router.post("/reminders/claim-due", response_model=list[ReminderRecord])
async def claim_due_reminders(request: Request) -> list[ReminderRecord]:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    return await asyncio.to_thread(
        request.app.state.memory_store.claim_due_reminders, now, 10
    )
