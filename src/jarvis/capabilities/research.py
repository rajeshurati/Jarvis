"""Opt-in web research contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ResearchError(RuntimeError):
    """Raised when an explicitly requested research operation cannot finish."""


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """A locally saved, source-linked research result."""

    query: str
    summary: str
    path: Path
    source_count: int


class ResearchTools(Protocol):
    """Research operations exposed to the safe command router."""

    def research(self, query: str) -> ResearchReport: ...
