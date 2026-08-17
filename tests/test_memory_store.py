"""SQLite memory behavior tests."""

from pathlib import Path

import pytest

from jarvis.adapters.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture
def memory(tmp_path: Path) -> SQLiteMemoryStore:
    store = SQLiteMemoryStore(tmp_path / "jarvis.db")
    store.initialize()
    return store


def test_memory_can_be_created_updated_filtered_and_deleted(
    memory: SQLiteMemoryStore,
) -> None:
    original = memory.remember("preference", "editor", "VS Code")
    updated = memory.remember("preference", "editor", "Cursor")
    memory.remember("career", "goal", "AI engineer")

    assert original.id == updated.id
    assert updated.value == "Cursor"
    assert [item.key for item in memory.list_memories("preference")] == ["editor"]
    assert memory.forget(updated.id)
    assert not memory.forget(updated.id)


def test_memory_rejects_invalid_values_and_roles(memory: SQLiteMemoryStore) -> None:
    with pytest.raises(ValueError, match="required"):
        memory.remember("", "key", "value")
    with pytest.raises(ValueError, match="role"):
        memory.append_conversation("system", "hidden")


def test_memory_search_is_local_and_bounded(memory: SQLiteMemoryStore) -> None:
    memory.remember("preference", "editor", "Visual Studio Code")
    memory.remember("preference", "drink", "coffee")

    matches = memory.search_memories("studio")

    assert [item.key for item in matches] == ["editor"]


def test_conversation_projects_tasks_and_context(memory: SQLiteMemoryStore) -> None:
    memory.append_conversation("user", "hello")
    memory.append_conversation("assistant", "Hello Rajesh")
    assert memory.recent_conversation(2) == [
        ("user", "hello"),
        ("assistant", "Hello Rajesh"),
    ]

    project = memory.create_project("Jarvis", "Build a local assistant", "2026-08-31")
    updated = memory.create_project("jarvis", "Ship the assistant")
    assert updated.id == project.id
    task = memory.add_project_task(project.id, "Finish memory")
    completed = memory.update_project_task(task.id, "completed")
    risk = memory.add_project_note(project.id, "risk", "Limited disk space")
    assert task.title == "Finish memory"
    assert memory.list_project_tasks(project.id) == [completed]
    assert memory.list_project_notes(project.id) == [risk]
    assert memory.list_projects()[0].objective == "Ship the assistant"
    assert "Ship the assistant" in memory.context_summary()
    assert "Limited disk space" in memory.context_summary()


def test_project_and_task_validation(memory: SQLiteMemoryStore) -> None:
    with pytest.raises(ValueError, match="required"):
        memory.create_project("", "objective")
    project = memory.create_project("Jarvis", "Build it")
    with pytest.raises(ValueError, match="required"):
        memory.add_project_task(project.id, " ")


def test_reminders_are_persistent_and_claimed_once(memory: SQLiteMemoryStore) -> None:
    future = memory.create_reminder("Call the dentist", "2026-08-02T12:00:00+00:00")
    due = memory.create_reminder("Stretch", "2026-08-01T12:00:00+00:00")

    assert [item.id for item in memory.list_reminders()] == [due.id, future.id]
    claimed = memory.claim_due_reminders("2026-08-01T12:00:01+00:00")
    assert claimed == [type(due)(due.id, due.title, due.due_at, "delivered")]
    assert memory.claim_due_reminders("2026-08-01T12:00:01+00:00") == []
    assert memory.list_reminders() == [future]


def test_reminder_validation(memory: SQLiteMemoryStore) -> None:
    with pytest.raises(ValueError, match="required"):
        memory.create_reminder("", "2026-08-01T12:00:00+00:00")
    with pytest.raises(ValueError, match="between"):
        memory.claim_due_reminders("2026-08-01T12:00:00+00:00", 0)


def test_audit_events_are_immutable_bounded_and_newest_first(
    memory: SQLiteMemoryStore,
) -> None:
    first = memory.append_audit("request", "received", None, "hello", "accepted")
    second = memory.append_audit("response", "completed", "read_time", "time", "done")

    assert [item.id for item in memory.list_audit()] == [second.id, first.id]
    assert second.action == "read_time"
    with pytest.raises(ValueError, match="between"):
        memory.list_audit(0)


def test_workflow_schema_validates_and_orders_steps(memory: SQLiteMemoryStore) -> None:
    workflow = memory.create_workflow("Morning", ["open calculator", "tell me the time"])
    steps = memory.list_workflow_steps(workflow.id)

    assert workflow.total_steps == 2
    assert [step.position for step in steps] == [0, 1]
    assert memory.list_workflows()[0].name == "Morning"
    with pytest.raises(ValueError, match="already exists"):
        memory.create_workflow("morning", ["duplicate"])
