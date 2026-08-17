"""Durable workflow execution and recovery tests."""

from pathlib import Path

from jarvis.adapters.memory.sqlite_store import SQLiteMemoryStore
from jarvis.application.workflow_service import WorkflowService
from jarvis.capabilities.automation import ActionResult


class Executor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def try_execute(self, command: str) -> ActionResult | None:
        self.commands.append(command)
        if command == "unsupported":
            return None
        if command == "type hello":
            return ActionResult("confirm_desktop_action", "Confirm typing.")
        return ActionResult("safe_action", f"Completed {command}.")


def build(tmp_path: Path) -> tuple[SQLiteMemoryStore, WorkflowService, Executor]:
    memory = SQLiteMemoryStore(tmp_path / "jarvis.db")
    memory.initialize()
    service = WorkflowService(memory)
    executor = Executor()
    service.bind_executor(executor)
    return memory, service, executor


def test_workflow_completes_and_checkpoints_each_step(tmp_path: Path) -> None:
    memory, service, executor = build(tmp_path)
    workflow = service.create("Morning", ["open calculator", "what time is it"])

    result = service.run(workflow.id)

    assert result.action == "workflow_completed"
    assert executor.commands == ["open calculator", "what time is it"]
    assert memory.get_workflow(workflow.id).status == "completed"  # type: ignore[union-attr]
    assert all(step.status == "completed" for step in memory.list_workflow_steps(workflow.id))


def test_workflow_pauses_for_confirmation_and_resumes(tmp_path: Path) -> None:
    memory, service, executor = build(tmp_path)
    workflow = service.create("Form", ["type hello", "press enter"])

    paused = service.run(workflow.id)
    resumed = service.confirmation_completed()

    assert paused.action == "workflow_paused"
    assert resumed and resumed.action == "workflow_completed"
    assert executor.commands == ["type hello", "press enter"]
    assert memory.get_workflow(workflow.id).current_position == 2  # type: ignore[union-attr]


def test_workflow_failure_survives_store_reopen(tmp_path: Path) -> None:
    _, service, _ = build(tmp_path)
    workflow = service.create("Broken", ["unsupported"])
    assert service.run(workflow.id).action == "workflow_failed"

    reopened = SQLiteMemoryStore(tmp_path / "jarvis.db")
    reopened.initialize()
    restored = reopened.get_workflow(workflow.id)
    assert restored and restored.status == "failed"
    assert restored.last_error == "No typed tool supports this step."


def test_workflow_can_be_cancelled(tmp_path: Path) -> None:
    memory, service, _ = build(tmp_path)
    workflow = service.create("Later", ["open calculator"])
    assert service.cancel(workflow.id).action == "cancel_workflow"
    assert memory.get_workflow(workflow.id).status == "cancelled"  # type: ignore[union-attr]


def test_workflow_reports_unavailable_missing_and_terminal_states(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "jarvis.db")
    memory.initialize()
    unbound = WorkflowService(memory)
    workflow = unbound.create("One", ["open calculator"])
    assert unbound.run(workflow.id).action == "workflow_unavailable"
    assert unbound.cancel(999).action == "workflow_not_found"

    executor = Executor()
    unbound.bind_executor(executor)
    assert unbound.run(999).action == "workflow_not_found"
    assert unbound.run(workflow.id).action == "workflow_completed"
    assert unbound.run(workflow.id).action == "workflow_completed"
    assert unbound.confirmation_completed() is None


def test_nested_workflow_is_rejected(tmp_path: Path) -> None:
    _, service, _ = build(tmp_path)
    workflow = service.create("Nested", ["run workflow 999"])
    result = service.run(workflow.id)
    assert result.action == "workflow_failed"
    assert "Nested workflows" in result.message
