"""Local planner validation tests."""

import pytest

from jarvis.application.planner_service import LocalPlannerService
from jarvis.capabilities.language import LanguageMessage
from jarvis.capabilities.memory import WorkflowRecord


class Model:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def complete(self, messages: list[LanguageMessage]) -> str:
        assert messages[-1].role == "user"
        return self.answer


class Workflows:
    def create(self, name: str, commands: list[str]) -> WorkflowRecord:
        return WorkflowRecord(7, name, "ready", 0, len(commands), None)


def test_planner_saves_validated_draft() -> None:
    planner = LocalPlannerService(
        Model('{"name":"Morning setup","steps":["open gmail","show reminders"]}'),
        Workflows(),
    )
    workflow = planner.create("prepare for work")
    assert workflow.name == "Morning setup"
    assert workflow.total_steps == 2


def test_planner_rejects_high_impact_step() -> None:
    planner = LocalPlannerService(
        Model('{"name":"Bad","steps":["open gmail","delete all files"]}'), Workflows()
    )
    with pytest.raises(ValueError, match="high-impact"):
        planner.create("clean up")


def test_planner_rejects_unsupported_physical_step() -> None:
    planner = LocalPlannerService(
        Model('{"name":"Bad","steps":["open notepad","remove the laptop cover"]}'),
        Workflows(),
    )
    with pytest.raises(ValueError, match="unsupported"):
        planner.create("prepare laptop")


def test_planner_rejects_empty_goal_and_invalid_json() -> None:
    planner = LocalPlannerService(Model("not json"), Workflows())
    with pytest.raises(ValueError, match="planning goal"):
        planner.create(" ")
    with pytest.raises(ValueError, match="valid JSON"):
        planner.create("prepare work")


def test_planner_rejects_unsafe_goal_before_model() -> None:
    planner = LocalPlannerService(Model("not used"), Workflows())
    with pytest.raises(ValueError, match="human or high-impact"):
        planner.create("disassemble my laptop")
