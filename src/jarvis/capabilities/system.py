"""Bounded operating-system control contracts."""

from __future__ import annotations

from typing import Protocol


class SystemControlError(RuntimeError):
    """Raised when a bounded local system operation fails."""


class SystemController(Protocol):
    """Safe Windows status and reversible setting operations."""

    def describe(self) -> str: ...
    def open_settings(self, section: str) -> None: ...
    def adjust_volume(self, operation: str) -> None: ...
