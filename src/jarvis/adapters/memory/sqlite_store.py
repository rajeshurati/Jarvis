"""SQLite-backed authoritative Jarvis memory."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jarvis.capabilities.memory import (
    AuditRecord,
    MemoryRecord,
    PresenceEventRecord,
    ProjectNoteRecord,
    ProjectRecord,
    ProjectTaskRecord,
    ReminderRecord,
    WorkflowRecord,
    WorkflowStepRecord,
)


class SQLiteMemoryStore:
    """Store editable preferences, conversation, projects, and next actions locally."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        """Create the idempotent local schema."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(category, key)
                );
                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    deadline TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS project_tasks (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS project_notes (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK(kind IN ('milestone','risk','dependency')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','resolved','completed')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'delivered', 'cancelled')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS reminders_due_idx
                    ON reminders(status, due_at);
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    action TEXT,
                    command TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS audit_events_created_idx
                    ON audit_events(created_at DESC, id DESC);
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    status TEXT NOT NULL DEFAULT 'ready'
                        CHECK(status IN (
                            'ready','running','paused','completed','cancelled','failed'
                        )),
                    current_position INTEGER NOT NULL DEFAULT 0,
                    total_steps INTEGER NOT NULL,
                    last_error TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id INTEGER PRIMARY KEY,
                    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN (
                            'pending','running','waiting_confirmation',
                            'completed','failed','cancelled'
                        )),
                    result TEXT,
                    UNIQUE(workflow_id, position)
                );
                CREATE TABLE IF NOT EXISTS presence_events (
                    id INTEGER PRIMARY KEY,
                    state TEXT NOT NULL CHECK(state IN ('present','vacant','entered','left')),
                    faces INTEGER NOT NULL CHECK(faces >= 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS presence_events_created_idx
                    ON presence_events(created_at DESC, id DESC);
                """
            )

    @staticmethod
    def _memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(row["id"], row["category"], row["key"], row["value"], row["updated_at"])

    @staticmethod
    def _project(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(
            row["id"], row["name"], row["objective"], row["status"], row["deadline"]
        )

    @staticmethod
    def _task(row: sqlite3.Row) -> ProjectTaskRecord:
        return ProjectTaskRecord(row["id"], row["project_id"], row["title"], row["status"])

    @staticmethod
    def _project_note(row: sqlite3.Row) -> ProjectNoteRecord:
        return ProjectNoteRecord(
            row["id"], row["project_id"], row["kind"], row["content"], row["status"]
        )

    @staticmethod
    def _reminder(row: sqlite3.Row) -> ReminderRecord:
        return ReminderRecord(row["id"], row["title"], row["due_at"], row["status"])

    @staticmethod
    def _audit(row: sqlite3.Row) -> AuditRecord:
        return AuditRecord(
            row["id"], row["event_type"], row["status"], row["action"],
            row["command"], row["detail"], row["created_at"]
        )

    @staticmethod
    def _workflow(row: sqlite3.Row) -> WorkflowRecord:
        return WorkflowRecord(
            row["id"], row["name"], row["status"], row["current_position"],
            row["total_steps"], row["last_error"]
        )

    @staticmethod
    def _workflow_step(row: sqlite3.Row) -> WorkflowStepRecord:
        return WorkflowStepRecord(
            row["id"], row["workflow_id"], row["position"], row["command"],
            row["status"], row["result"]
        )

    @staticmethod
    def _presence(row: sqlite3.Row) -> PresenceEventRecord:
        return PresenceEventRecord(row["id"], row["state"], row["faces"], row["created_at"])

    def remember(self, category: str, key: str, value: str) -> MemoryRecord:
        """Upsert one normalized memory item."""
        category, key, value = category.strip(), key.strip(), value.strip()
        if not category or not key or not value:
            raise ValueError("Memory category, key, and value are required")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO memories(category, key, value) VALUES (?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
                (category, key, value),
            )
            row = connection.execute(
                "SELECT * FROM memories WHERE category=? AND key=?",
                (category, key),
            ).fetchone()
        if row is None:
            raise RuntimeError("Memory upsert did not return a row")
        return self._memory(row)

    def list_memories(self, category: str | None = None) -> list[MemoryRecord]:
        """List memories newest first."""
        query = "SELECT * FROM memories"
        parameters: tuple[str, ...] = ()
        if category:
            query += " WHERE category=?"
            parameters = (category,)
        query += " ORDER BY updated_at DESC, id DESC"
        with self._connect() as connection:
            return [self._memory(row) for row in connection.execute(query, parameters)]

    def search_memories(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        """Rank bounded local keyword matches across category, key, and value."""
        terms = [item for item in query.casefold().split() if len(item) > 1][:8]
        if not terms or not 1 <= limit <= 100:
            raise ValueError("Memory search needs a query and a limit between 1 and 100")
        clauses: list[str] = []
        parameters: list[str | int] = []
        for term in terms:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            clauses.append(
                "(lower(category) LIKE ? ESCAPE '\\' OR lower(key) LIKE ? ESCAPE '\\' "
                "OR lower(value) LIKE ? ESCAPE '\\')"
            )
            parameters.extend((pattern, pattern, pattern))
        parameters.append(limit)
        sql = (
            "SELECT * FROM memories WHERE "
            + " OR ".join(clauses)
            + " ORDER BY updated_at DESC, id DESC LIMIT ?"
        )
        with self._connect() as connection:
            return [self._memory(row) for row in connection.execute(sql, parameters)]

    def forget(self, memory_id: int) -> bool:
        """Delete one explicit memory item."""
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            return cursor.rowcount > 0

    def append_conversation(self, role: str, content: str) -> None:
        """Persist conversation and cap it at 500 events."""
        if role not in {"user", "assistant"}:
            raise ValueError("Conversation role must be user or assistant")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversation(role, content) VALUES (?, ?)",
                (role, content[:8_000]),
            )
            connection.execute(
                """DELETE FROM conversation WHERE id NOT IN
                (SELECT id FROM conversation ORDER BY id DESC LIMIT 500)"""
            )

    def recent_conversation(self, limit: int) -> list[tuple[str, str]]:
        """Return the latest events in chronological order."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content FROM conversation ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(row["role"], row["content"]) for row in reversed(rows)]

    def create_project(
        self,
        name: str,
        objective: str,
        deadline: str | None = None,
    ) -> ProjectRecord:
        """Upsert a project without discarding its tasks."""
        name, objective = name.strip(), objective.strip()
        if not name or not objective:
            raise ValueError("Project name and objective are required")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO projects(name, objective, deadline) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET objective=excluded.objective,
                deadline=excluded.deadline, updated_at=CURRENT_TIMESTAMP""",
                (name, objective, deadline),
            )
            row = connection.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()
        if row is None:
            raise RuntimeError("Project upsert did not return a row")
        return self._project(row)

    def list_projects(self) -> list[ProjectRecord]:
        """List active projects first."""
        with self._connect() as connection:
            return [
                self._project(row)
                for row in connection.execute(
                    "SELECT * FROM projects ORDER BY status='active' DESC, updated_at DESC"
                )
            ]

    def add_project_task(self, project_id: int, title: str) -> ProjectTaskRecord:
        """Add one non-empty project action."""
        if not title.strip():
            raise ValueError("Task title is required")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO project_tasks(project_id, title) VALUES (?, ?)",
                (project_id, title.strip()),
            )
            row = connection.execute(
                "SELECT * FROM project_tasks WHERE id=?",
                (cursor.lastrowid,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Task insert did not return a row")
        return self._task(row)

    def list_project_tasks(self, project_id: int) -> list[ProjectTaskRecord]:
        """List pending actions before completed ones."""
        with self._connect() as connection:
            return [
                self._task(row)
                for row in connection.execute(
                    """SELECT * FROM project_tasks WHERE project_id=?
                    ORDER BY status='pending' DESC, id""",
                    (project_id,),
                )
            ]

    def update_project_task(self, task_id: int, status: str) -> ProjectTaskRecord:
        """Update one task to a bounded lifecycle status."""
        if status not in {"pending", "in_progress", "completed", "cancelled"}:
            raise ValueError("Project task status is invalid")
        with self._connect() as connection:
            connection.execute(
                "UPDATE project_tasks SET status=? WHERE id=?", (status, task_id)
            )
            row = connection.execute(
                "SELECT * FROM project_tasks WHERE id=?", (task_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Project task not found")
        return self._task(row)

    def add_project_note(self, project_id: int, kind: str, content: str) -> ProjectNoteRecord:
        """Persist one structured milestone, risk, or dependency."""
        kind, content = kind.casefold().strip(), content.strip()
        if kind not in {"milestone", "risk", "dependency"} or not content:
            raise ValueError("Project note kind or content is invalid")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO project_notes(project_id,kind,content) VALUES (?,?,?)",
                (project_id, kind, content[:2_000]),
            )
            row = connection.execute(
                "SELECT * FROM project_notes WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Project note insert did not return a row")
        return self._project_note(row)

    def list_project_notes(self, project_id: int) -> list[ProjectNoteRecord]:
        """List unresolved planning notes first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM project_notes WHERE project_id=? "
                "ORDER BY status='open' DESC, id",
                (project_id,),
            ).fetchall()
        return [self._project_note(row) for row in rows]

    def create_reminder(self, title: str, due_at: str) -> ReminderRecord:
        """Persist a non-empty reminder using an ISO-8601 due time."""
        title, due_at = title.strip(), due_at.strip()
        if not title or not due_at:
            raise ValueError("Reminder title and due time are required")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders(title, due_at) VALUES (?, ?)", (title, due_at)
            )
            row = connection.execute(
                "SELECT * FROM reminders WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Reminder insert did not return a row")
        return self._reminder(row)

    def list_reminders(self, include_delivered: bool = False) -> list[ReminderRecord]:
        """List upcoming reminders first."""
        query = "SELECT * FROM reminders"
        if not include_delivered:
            query += " WHERE status='pending'"
        query += " ORDER BY due_at, id"
        with self._connect() as connection:
            return [self._reminder(row) for row in connection.execute(query)]

    def claim_due_reminders(self, now: str, limit: int = 10) -> list[ReminderRecord]:
        """Atomically claim due reminders so concurrent pollers cannot repeat them."""
        if limit < 1 or limit > 100:
            raise ValueError("Reminder claim limit must be between 1 and 100")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT * FROM reminders
                WHERE status='pending' AND due_at<=?
                ORDER BY due_at, id LIMIT ?""",
                (now, limit),
            ).fetchall()
            if rows:
                placeholders = ",".join("?" for _ in rows)
                connection.execute(
                    f"UPDATE reminders SET status='delivered' WHERE id IN ({placeholders})",
                    tuple(row["id"] for row in rows),
                )
        return [ReminderRecord(row["id"], row["title"], row["due_at"], "delivered") for row in rows]

    def append_audit(
        self, event_type: str, status: str, action: str | None, command: str, detail: str
    ) -> AuditRecord:
        """Append one immutable event while bounding every stored field."""
        values = tuple(value.strip() for value in (event_type, status, command, detail))
        if not values[0] or not values[1]:
            raise ValueError("Audit event type and status are required")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO audit_events(event_type,status,action,command,detail)
                VALUES (?,?,?,?,?)""",
                (values[0][:50], values[1][:50], action[:100] if action else None,
                 values[2][:500], values[3][:1000]),
            )
            row = connection.execute(
                "SELECT * FROM audit_events WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Audit insert did not return a row")
        return self._audit(row)

    def list_audit(self, limit: int = 100) -> list[AuditRecord]:
        """Return newest immutable events with a strict query bound."""
        if limit < 1 or limit > 500:
            raise ValueError("Audit limit must be between 1 and 500")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._audit(row) for row in rows]

    def append_presence_event(self, state: str, faces: int) -> PresenceEventRecord:
        """Store one bounded occupancy transition."""
        if state not in {"present", "vacant", "entered", "left"} or faces < 0:
            raise ValueError("Presence event is invalid")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO presence_events(state,faces) VALUES (?,?)", (state, faces)
            )
            row = connection.execute(
                "SELECT * FROM presence_events WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Presence event insert did not return a row")
        return self._presence(row)

    def list_presence_events(self, limit: int = 100) -> list[PresenceEventRecord]:
        """Return newest occupancy transitions with a strict bound."""
        if not 1 <= limit <= 500:
            raise ValueError("Presence event limit must be between 1 and 500")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM presence_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._presence(row) for row in rows]

    def create_workflow(self, name: str, commands: list[str]) -> WorkflowRecord:
        """Create an ordered workflow and all steps in one transaction."""
        name = name.strip()
        commands = [command.strip() for command in commands if command.strip()]
        if not name or not 1 <= len(commands) <= 20 or any(len(item) > 500 for item in commands):
            raise ValueError("Workflow requires a name and 1 to 20 bounded steps")
        with self._connect() as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO workflows(name,total_steps) VALUES (?,?)", (name, len(commands))
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("Workflow insert returned no identifier")
                workflow_id = cursor.lastrowid
                connection.executemany(
                    "INSERT INTO workflow_steps(workflow_id,position,command) VALUES (?,?,?)",
                    [(workflow_id, position, command) for position, command in enumerate(commands)],
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("A workflow with that name already exists") from error
            row = connection.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Workflow insert did not return a row")
        return self._workflow(row)

    def list_workflows(self) -> list[WorkflowRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM workflows ORDER BY
                status IN ('ready','running','paused') DESC, updated_at DESC, id DESC"""
            ).fetchall()
        return [self._workflow(row) for row in rows]

    def get_workflow(self, workflow_id: int) -> WorkflowRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
        return self._workflow(row) if row is not None else None

    def list_workflow_steps(self, workflow_id: int) -> list[WorkflowStepRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY position", (workflow_id,)
            ).fetchall()
        return [self._workflow_step(row) for row in rows]

    def checkpoint_workflow(
        self, workflow_id: int, status: str, current_position: int,
        last_error: str | None = None,
    ) -> WorkflowRecord:
        with self._connect() as connection:
            connection.execute(
                """UPDATE workflows SET status=?,current_position=?,last_error=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (status, current_position, last_error, workflow_id),
            )
            row = connection.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Workflow not found")
        return self._workflow(row)

    def checkpoint_workflow_step(
        self, step_id: int, status: str, result: str | None = None
    ) -> WorkflowStepRecord:
        with self._connect() as connection:
            connection.execute(
                "UPDATE workflow_steps SET status=?,result=? WHERE id=?",
                (status, result[:1000] if result else None, step_id),
            )
            row = connection.execute(
                "SELECT * FROM workflow_steps WHERE id=?", (step_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Workflow step not found")
        return self._workflow_step(row)

    def context_summary(self) -> str:
        """Build a compact prompt-safe summary from authoritative rows."""
        memories = self.list_memories()[:20]
        projects = self.list_projects()[:10]
        reminders = self.list_reminders()[:10]
        lines = ["Local user memory:"]
        lines.extend(f"- [{item.category}] {item.key}: {item.value}" for item in memories)
        lines.append("Tracked projects:")
        for project in projects:
            deadline = f", deadline {project.deadline}" if project.deadline else ""
            lines.append(f"- {project.name}: {project.objective} ({project.status}{deadline})")
            lines.extend(
                f"  - {task.status}: {task.title}"
                for task in self.list_project_tasks(project.id)[:5]
            )
            lines.extend(
                f"  - {note.kind} ({note.status}): {note.content}"
                for note in self.list_project_notes(project.id)[:5]
            )
        lines.append("Upcoming reminders:")
        lines.extend(f"- {item.title} at {item.due_at}" for item in reminders)
        return "\n".join(lines)
