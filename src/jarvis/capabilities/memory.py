"""Persistent local-memory contracts and values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """One user-editable memory item."""

    id: int
    category: str
    key: str
    value: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    """One tracked project and its current status."""

    id: int
    name: str
    objective: str
    status: str
    deadline: str | None


@dataclass(frozen=True, slots=True)
class ProjectTaskRecord:
    """One next action attached to a project."""

    id: int
    project_id: int
    title: str
    status: str


@dataclass(frozen=True, slots=True)
class ProjectNoteRecord:
    """One milestone, risk, or dependency attached to a project."""

    id: int
    project_id: int
    kind: str
    content: str
    status: str


@dataclass(frozen=True, slots=True)
class ReminderRecord:
    """One persistent local reminder or timer."""

    id: int
    title: str
    due_at: str
    status: str


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable local record of one assistant or tool event."""

    id: int
    event_type: str
    status: str
    action: str | None
    command: str
    detail: str
    created_at: str


@dataclass(frozen=True, slots=True)
class WorkflowRecord:
    """Durable workflow state that survives process restarts."""

    id: int
    name: str
    status: str
    current_position: int
    total_steps: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class WorkflowStepRecord:
    """One ordered command and its checkpoint state."""

    id: int
    workflow_id: int
    position: int
    command: str
    status: str
    result: str | None


@dataclass(frozen=True, slots=True)
class PresenceEventRecord:
    """One locally observed room occupancy transition."""

    id: int
    state: str
    faces: int
    created_at: str


class MemoryStore(Protocol):
    """Authoritative local memory with explicit edit and deletion operations."""

    def initialize(self) -> None:
        """Create or migrate the local schema."""

    def remember(self, category: str, key: str, value: str) -> MemoryRecord:
        """Create or replace a memory item."""

    def list_memories(self, category: str | None = None) -> list[MemoryRecord]:
        """List current memory items."""

    def search_memories(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        """Search user-editable local memory without sending it elsewhere."""

    def forget(self, memory_id: int) -> bool:
        """Delete one memory item by identifier."""

    def append_conversation(self, role: str, content: str) -> None:
        """Persist one bounded conversation event."""

    def recent_conversation(self, limit: int) -> list[tuple[str, str]]:
        """Return recent conversation in chronological order."""

    def create_project(
        self,
        name: str,
        objective: str,
        deadline: str | None = None,
    ) -> ProjectRecord:
        """Create or update one project."""

    def list_projects(self) -> list[ProjectRecord]:
        """List active and completed projects."""

    def add_project_task(self, project_id: int, title: str) -> ProjectTaskRecord:
        """Create one next action for a project."""

    def list_project_tasks(self, project_id: int) -> list[ProjectTaskRecord]:
        """List project actions."""

    def update_project_task(self, task_id: int, status: str) -> ProjectTaskRecord:
        """Change one project action status."""

    def add_project_note(self, project_id: int, kind: str, content: str) -> ProjectNoteRecord:
        """Attach a milestone, risk, or dependency to a project."""

    def list_project_notes(self, project_id: int) -> list[ProjectNoteRecord]:
        """List structured project planning notes."""

    def create_reminder(self, title: str, due_at: str) -> ReminderRecord:
        """Create one persistent reminder."""

    def list_reminders(self, include_delivered: bool = False) -> list[ReminderRecord]:
        """List pending reminders, optionally including delivered entries."""

    def claim_due_reminders(self, now: str, limit: int = 10) -> list[ReminderRecord]:
        """Atomically mark and return reminders due at or before ``now``."""

    def append_audit(
        self, event_type: str, status: str, action: str | None, command: str, detail: str
    ) -> AuditRecord:
        """Append one immutable, privacy-bounded audit event."""

    def list_audit(self, limit: int = 100) -> list[AuditRecord]:
        """List newest audit events first."""

    def append_presence_event(self, state: str, faces: int) -> PresenceEventRecord:
        """Persist one room occupancy transition without storing an image."""

    def list_presence_events(self, limit: int = 100) -> list[PresenceEventRecord]:
        """List newest room occupancy transitions first."""

    def create_workflow(self, name: str, commands: list[str]) -> WorkflowRecord:
        """Create a durable ordered workflow."""

    def list_workflows(self) -> list[WorkflowRecord]:
        """List workflows with active work first."""

    def get_workflow(self, workflow_id: int) -> WorkflowRecord | None:
        """Return one workflow when it exists."""

    def list_workflow_steps(self, workflow_id: int) -> list[WorkflowStepRecord]:
        """Return ordered workflow steps."""

    def checkpoint_workflow(
        self,
        workflow_id: int,
        status: str,
        current_position: int,
        last_error: str | None = None,
    ) -> WorkflowRecord:
        """Persist the workflow cursor and status."""

    def checkpoint_workflow_step(
        self, step_id: int, status: str, result: str | None = None
    ) -> WorkflowStepRecord:
        """Persist one step result."""

    def context_summary(self) -> str:
        """Return concise memory and project context for the local model."""
