"""Local language-model contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LanguageModelError(RuntimeError):
    """Raised when the configured local language model cannot answer."""


@dataclass(frozen=True, slots=True)
class LanguageMessage:
    """One role-tagged conversation message."""

    role: str
    content: str


class LanguageModel(Protocol):
    """Generate a reply from bounded conversation history."""

    def complete(self, messages: list[LanguageMessage]) -> str:
        """Return one assistant response."""
