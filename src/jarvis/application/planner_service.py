"""Local model planning that produces safe, resumable workflow drafts."""

from __future__ import annotations

import json
import re
from typing import Protocol

from jarvis.capabilities.language import LanguageMessage, LanguageModel
from jarvis.capabilities.memory import WorkflowRecord


class WorkflowDraftStore(Protocol):
    """Minimum workflow contract needed by the planner."""

    def create(self, name: str, commands: list[str]) -> WorkflowRecord: ...


class LocalPlannerService:
    """Ask the local model for a plan, validate it, and save it without executing."""

    def __init__(self, model: LanguageModel, workflows: WorkflowDraftStore) -> None:
        self._model = model
        self._workflows = workflows

    _safe_commands = (
        re.compile(
            r"open (?:calculator|notepad|file explorer|explorer|paint|settings|google|"
            r"youtube|gmail|github)$",
            re.I,
        ),
        re.compile(
            r"(?:what time is it|tell me the time|what is the date|tell me the date)$", re.I
        ),
        re.compile(r"(?:show|list) (?:reminders|projects|workflows)$", re.I),
        re.compile(r"(?:system|computer|laptop) status$", re.I),
        re.compile(r"(?:what is on|describe|read|summarize) my screen$", re.I),
        re.compile(r"(?:find|search for|look for) (?:a |the )?(?:file )?(?:named )?.+$", re.I),
        re.compile(r"summarize (?:the )?(?:document|file) .+$", re.I),
        re.compile(
            r"(?:run jarvis tests|lint jarvis|check jarvis types|show (?:python|git|docker|"
            r"kubectl|terraform) version)$",
            re.I,
        ),
    )

    def create(self, goal: str) -> WorkflowRecord:
        """Create a bounded workflow draft; every later step still passes the tool router."""
        clean_goal = re.sub(r"\s+", " ", goal).strip()
        if not clean_goal or len(clean_goal) > 1_000:
            raise ValueError("A planning goal between 1 and 1000 characters is required")
        unsafe_goal = re.compile(
            r"\b(?:disassemble|take apart|remove (?:the )?cover|wipe|format|shutdown|"
            r"purchase|buy|delete)\b",
            re.I,
        )
        if unsafe_goal.search(clean_goal):
            raise ValueError("That goal needs human or high-impact action and was not planned")
        response = self._model.complete(
            [
                LanguageMessage(
                    "system",
                    "Return JSON only: {\"name\":\"short name\",\"steps\":[\"command\"]}. "
                    "Create 2 to 8 concrete, concise steps. Do not include passwords, purchases, "
                    "deletion, shutdown, physical-device work, or claims that work already "
                    "happened. "
                    "Use only commands such as open notepad, open gmail, show reminders, system "
                    "status, describe my screen, find file NAME, summarize document NAME, run "
                    "Jarvis tests, lint Jarvis, or check Jarvis types. "
                    "Plans are drafts.",
                ),
                LanguageMessage("user", clean_goal),
            ]
        )
        payload = self._parse(response)
        name = re.sub(r"\s+", " ", str(payload.get("name", "")).strip())[:100]
        raw_steps = payload.get("steps")
        if not name or not isinstance(raw_steps, list) or not 2 <= len(raw_steps) <= 8:
            raise ValueError("The local planner returned an invalid workflow")
        steps = [
            re.sub(r"^\d+[.)]\s*", "", re.sub(r"\s+", " ", str(step)).strip())[:500]
            for step in raw_steps
        ]
        if any(not step for step in steps):
            raise ValueError("The local planner returned an empty workflow step")
        forbidden = re.compile(
            r"\b(?:password|secret|purchase|buy|delete|recycle|shutdown|format|wipe)\b", re.I
        )
        if any(forbidden.search(step) for step in steps):
            raise ValueError("The plan contains a high-impact step and was not saved")
        if any(re.search(r"\b(?:NAME|TITLE|PATH|TODO)\b", step) for step in steps):
            raise ValueError("The plan contains an unresolved placeholder and was not saved")
        unsupported = any(
            not any(pattern.fullmatch(step) for pattern in self._safe_commands) for step in steps
        )
        if unsupported:
            raise ValueError("The plan contains an unsupported automation step and was not saved")
        return self._workflows.create(name, steps)

    @staticmethod
    def _parse(response: str) -> dict[str, object]:
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.I)
        try:
            value = json.loads(fenced)
        except json.JSONDecodeError as error:
            raise ValueError("The local planner did not return valid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("The local planner returned an invalid workflow")
        return value
