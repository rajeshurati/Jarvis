"""Durable, checkpointed execution of ordered Jarvis commands."""

from __future__ import annotations

from jarvis.capabilities.automation import ActionResult, DesktopAutomation
from jarvis.capabilities.memory import MemoryStore, WorkflowRecord


class WorkflowService:
    """Execute bounded command workflows and persist every transition."""

    def __init__(self, memory: MemoryStore) -> None:
        self._memory = memory
        self._executor: DesktopAutomation | None = None

    def bind_executor(self, executor: DesktopAutomation) -> None:
        """Bind the typed tool router after composition resolves the cycle."""
        self._executor = executor

    def create(self, name: str, commands: list[str]) -> WorkflowRecord:
        return self._memory.create_workflow(name, commands)

    def list(self) -> list[WorkflowRecord]:
        return self._memory.list_workflows()

    def cancel(self, workflow_id: int) -> ActionResult:
        workflow = self._memory.get_workflow(workflow_id)
        if workflow is None:
            return ActionResult("workflow_not_found", "That workflow does not exist.")
        for step in self._memory.list_workflow_steps(workflow_id):
            if step.status in {"pending", "running", "waiting_confirmation"}:
                self._memory.checkpoint_workflow_step(step.id, "cancelled", "Cancelled by user.")
        self._memory.checkpoint_workflow(
            workflow_id, "cancelled", workflow.current_position, "Cancelled by user."
        )
        return ActionResult("cancel_workflow", f"Workflow {workflow.name} cancelled.")

    def run(self, workflow_id: int) -> ActionResult:
        """Run safe steps until completion, failure, or a confirmation checkpoint."""
        if self._executor is None:
            return ActionResult("workflow_unavailable", "Workflow execution is unavailable.")
        workflow = self._memory.get_workflow(workflow_id)
        if workflow is None:
            return ActionResult("workflow_not_found", "That workflow does not exist.")
        if workflow.status == "completed":
            return ActionResult("workflow_completed", f"Workflow {workflow.name} is complete.")
        if workflow.status == "cancelled":
            return ActionResult("workflow_cancelled", f"Workflow {workflow.name} is cancelled.")
        steps = self._memory.list_workflow_steps(workflow_id)
        position = workflow.current_position
        self._memory.checkpoint_workflow(workflow_id, "running", position)
        while position < len(steps):
            step = steps[position]
            if step.status == "completed":
                position += 1
                continue
            if step.command.casefold().startswith(
                ("create workflow", "run workflow", "resume workflow", "cancel workflow")
            ):
                return self._fail(workflow, step.id, position, "Nested workflows are not allowed.")
            self._memory.checkpoint_workflow_step(step.id, "running")
            result = self._executor.try_execute(step.command)
            if result is None:
                return self._fail(workflow, step.id, position, "No typed tool supports this step.")
            if result.action.startswith("confirm_"):
                self._memory.checkpoint_workflow_step(
                    step.id, "waiting_confirmation", result.message
                )
                self._memory.checkpoint_workflow(
                    workflow.id, "paused", position, "Confirmation required."
                )
                return ActionResult(
                    "workflow_paused",
                    f"Workflow {workflow.name} paused. {result.message}",
                )
            if any(marker in result.action for marker in ("error", "unavailable", "not_found")):
                return self._fail(workflow, step.id, position, result.message)
            self._memory.checkpoint_workflow_step(step.id, "completed", result.message)
            position += 1
            self._memory.checkpoint_workflow(workflow.id, "running", position)
        self._memory.checkpoint_workflow(workflow.id, "completed", position)
        return ActionResult("workflow_completed", f"Workflow {workflow.name} completed.")

    def confirmation_completed(self) -> ActionResult | None:
        """Advance the newest workflow waiting on the just-completed confirmation."""
        for workflow in self._memory.list_workflows():
            if workflow.status != "paused":
                continue
            steps = self._memory.list_workflow_steps(workflow.id)
            if workflow.current_position >= len(steps):
                continue
            step = steps[workflow.current_position]
            if step.status != "waiting_confirmation":
                continue
            self._memory.checkpoint_workflow_step(step.id, "completed", "Confirmed and executed.")
            self._memory.checkpoint_workflow(
                workflow.id, "ready", workflow.current_position + 1
            )
            return self.run(workflow.id)
        return None

    def _fail(
        self, workflow: WorkflowRecord, step_id: int, position: int, message: str
    ) -> ActionResult:
        self._memory.checkpoint_workflow_step(step_id, "failed", message)
        self._memory.checkpoint_workflow(workflow.id, "failed", position, message)
        return ActionResult("workflow_failed", f"Workflow {workflow.name} failed: {message}")
