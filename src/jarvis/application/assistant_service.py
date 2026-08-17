"""Conversation and safe-command orchestration."""

from __future__ import annotations

import asyncio
import re
from collections import deque
from dataclasses import dataclass

from jarvis.application.agent_orchestrator import AgentOrchestrator
from jarvis.application.conversation_policy import ConversationPolicy
from jarvis.capabilities.automation import DesktopAutomation
from jarvis.capabilities.language import LanguageMessage, LanguageModel
from jarvis.capabilities.memory import MemoryStore
from jarvis.core.persona import JARVIS_SYSTEM_PROMPT

SYSTEM_PROMPT = JARVIS_SYSTEM_PROMPT


@dataclass(frozen=True, slots=True)
class AssistantReply:
    """One response plus optional deterministic action metadata."""

    text: str
    action: str | None = None
    target_url: str | None = None
    desktop_action: str | None = None


class AssistantService:
    """Run safe commands first, otherwise consult the bounded local conversation."""

    def __init__(
        self,
        model: LanguageModel,
        automation: DesktopAutomation,
        history_messages: int = 12,
        memory: MemoryStore | None = None,
        conversation_policy: ConversationPolicy | None = None,
        agents: AgentOrchestrator | None = None,
    ) -> None:
        self._model = model
        self._automation = automation
        self._history: deque[LanguageMessage] = deque(maxlen=history_messages)
        self._history_messages = min(history_messages, 6)
        self._memory = memory
        self._conversation_policy = conversation_policy or ConversationPolicy()
        self._agents = agents or AgentOrchestrator()
        self._lock = asyncio.Lock()

    async def respond(self, text: str) -> AssistantReply:
        """Respond to one validated transcript without blocking the event loop."""
        command, topic_changed = self._conversation_policy.latest_intent(text)
        if not command or len(command) > 4_000:
            raise ValueError("Command must contain between 1 and 4000 characters")
        async with self._lock:
            await self._audit("request", "received", None, command, "Voice request accepted.")
            try:
                response = await self._respond_locked(command, topic_changed)
            except Exception as error:
                await self._audit(
                    "request", "failed", None, command, type(error).__name__
                )
                raise
            status = "pending_confirmation" if response.action and response.action.startswith(
                "confirm_"
            ) else "completed"
            await self._audit("response", status, response.action, command, response.text)
            return response

    async def _respond_locked(self, command: str, topic_changed: bool) -> AssistantReply:
        """Produce one response while the caller holds the conversation lock."""
        clarification = self._conversation_policy.clarification_for(command)
        if clarification is not None:
            await self._save_exchange(command, clarification)
            return AssistantReply(clarification)
        action = await asyncio.to_thread(self._automation.try_execute, command)
        if action is not None:
            reply = self._conversation_policy.spoken_reply(action.message)
            await self._save_exchange(command, reply)
            return AssistantReply(
                reply, action.action, action.target_url, action.desktop_action
            )
        agent = self._agents.select(command)
        system = f"{SYSTEM_PROMPT}\n\nActive specialist: {agent.name}. {agent.instruction}"
        history: list[LanguageMessage]
        if self._memory is None:
            history = list(self._history)
        else:
            context = await asyncio.to_thread(self._memory.context_summary)
            if context:
                system = f"{system}\n\n{context}"
            rows = await asyncio.to_thread(
                self._memory.recent_conversation, self._history_messages
            )
            history = [LanguageMessage(role, content) for role, content in rows]
        if topic_changed:
            history = []
        history = self._bounded_history(history)
        messages = [LanguageMessage("system", system), *history]
        messages.append(LanguageMessage("user", command))
        reply = await asyncio.to_thread(self._model.complete, messages)
        reply = self._conversation_policy.spoken_reply(reply)
        await self._save_exchange(command, reply)
        return AssistantReply(reply)

    async def _audit(
        self,
        event_type: str,
        status: str,
        action: str | None,
        command: str,
        detail: str,
    ) -> None:
        """Persist a redacted event without making auditing a new failure mode."""
        if self._memory is None:
            return
        sensitive = re.search(r"\b(?:type|password|passcode|secret|token|api key)\b", command, re.I)
        safe_command = "[REDACTED SENSITIVE COMMAND]" if sensitive else command
        safe_detail = "[REDACTED]" if sensitive else detail
        try:
            await asyncio.to_thread(
                self._memory.append_audit,
                event_type,
                status,
                action,
                safe_command,
                safe_detail,
            )
        except Exception:
            return

    async def _save_exchange(self, command: str, reply: str) -> None:
        """Persist locally when configured, otherwise keep bounded process memory."""
        if self._memory is None:
            self._history.extend(
                [LanguageMessage("user", command), LanguageMessage("assistant", reply)]
            )
            return
        await asyncio.to_thread(self._memory.append_conversation, "user", command)
        await asyncio.to_thread(self._memory.append_conversation, "assistant", reply)

    def _bounded_history(self, history: list[LanguageMessage]) -> list[LanguageMessage]:
        """Keep only short recent turns so old chat cannot dominate the current intent."""
        bounded: list[LanguageMessage] = []
        for message in history[-self._history_messages :]:
            content = re.sub(r"\s+", " ", message.content).strip()
            if message.role == "assistant":
                content = self._conversation_policy.spoken_reply(content)
            elif len(content) > 320:
                content = f"{content[:317].rsplit(' ', 1)[0]}..."
            bounded.append(LanguageMessage(message.role, content))
        return bounded
