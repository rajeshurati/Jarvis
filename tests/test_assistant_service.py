"""Conversation orchestration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.adapters.memory.sqlite_store import SQLiteMemoryStore
from jarvis.application.assistant_service import AssistantService
from jarvis.capabilities.automation import ActionResult
from jarvis.capabilities.language import LanguageMessage


class RecordingModel:
    def __init__(self) -> None:
        self.calls: list[list[LanguageMessage]] = []

    def complete(self, messages: list[LanguageMessage]) -> str:
        self.calls.append(messages)
        return "A concise local answer."


class StubAutomation:
    def __init__(self, result: ActionResult | None = None) -> None:
        self.result = result

    def try_execute(self, command: str) -> ActionResult | None:
        return self.result


@pytest.mark.anyio
async def test_safe_action_skips_language_model() -> None:
    model = RecordingModel()
    service = AssistantService(
        model,
        StubAutomation(ActionResult("open_application", "Opening calculator.")),
    )

    reply = await service.respond("open calculator")

    assert reply.action == "open_application"
    assert reply.text == "Opening calculator."
    assert model.calls == []


@pytest.mark.anyio
async def test_conversation_history_is_bounded_and_reused() -> None:
    model = RecordingModel()
    service = AssistantService(model, StubAutomation(), history_messages=2)

    await service.respond("first")
    await service.respond("second")

    second_messages = model.calls[1]
    assert [message.role for message in second_messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert second_messages[-1].content == "second"


@pytest.mark.anyio
async def test_empty_command_is_rejected() -> None:
    service = AssistantService(RecordingModel(), StubAutomation())

    try:
        await service.respond("   ")
    except ValueError as error:
        assert "between 1 and 4000" in str(error)
    else:
        raise AssertionError("Expected an empty command to be rejected")


@pytest.mark.anyio
async def test_incomplete_question_is_clarified_without_model() -> None:
    model = RecordingModel()
    service = AssistantService(model, StubAutomation())

    reply = await service.respond("What is?")

    assert reply.text == "Please finish your question. I am listening."
    assert model.calls == []


@pytest.mark.anyio
async def test_persistent_memory_is_injected_and_conversation_saved(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    memory.remember("preference", "editor", "VS Code")
    model = RecordingModel()
    service = AssistantService(model, StubAutomation(), memory=memory)

    await service.respond("help me code")

    assert "VS Code" in model.calls[0][0].content
    assert memory.recent_conversation(2)[0] == ("user", "help me code")
    assert [event.event_type for event in memory.list_audit()] == ["response", "request"]


@pytest.mark.anyio
async def test_sensitive_typed_text_is_redacted_from_audit(tmp_path: Path) -> None:
    memory = SQLiteMemoryStore(tmp_path / "memory.db")
    memory.initialize()
    service = AssistantService(RecordingModel(), StubAutomation(), memory=memory)

    await service.respond("type secret-password-123")

    assert all("secret-password-123" not in event.command for event in memory.list_audit())
