"""Typed contracts for local source-code artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class CodeGenerationError(RuntimeError):
    """Raised when generated source cannot be safely stored or validated."""


@dataclass(frozen=True, slots=True)
class CodeArtifact:
    """One locally generated source file and its validation result."""

    path: Path
    language: str
    syntax_valid: bool | None


class CodeTools(Protocol):
    """Generate code artifacts without executing them."""

    def generate(self, language: str, title: str, request: str) -> CodeArtifact:
        """Generate and locally validate one new source file."""

