"""Typed contracts for bounded local developer commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class DeveloperCommandError(RuntimeError):
    """Raised when a trusted developer check cannot complete."""


@dataclass(frozen=True, slots=True)
class DeveloperCommandResult:
    """Concise result from one fixed, non-shell command."""

    name: str
    succeeded: bool
    summary: str


class DeveloperTools(Protocol):
    """Run only predefined read-only or test commands."""

    def run(self, name: str) -> DeveloperCommandResult: ...

