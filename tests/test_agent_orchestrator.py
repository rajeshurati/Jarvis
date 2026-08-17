"""Specialist selection tests."""

from jarvis.application.agent_orchestrator import AgentOrchestrator


def test_selects_coding_specialist() -> None:
    profile = AgentOrchestrator().select("Fix this Python API bug")
    assert profile.name == "software engineer"


def test_defaults_to_executive_assistant() -> None:
    profile = AgentOrchestrator().select("How are you today?")
    assert profile.name == "executive assistant"
