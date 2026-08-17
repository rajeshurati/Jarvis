"""Typed desktop-automation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AutomationError(RuntimeError):
    """Raised when a recognized desktop action cannot be completed."""


class DesktopInputError(RuntimeError):
    """Raised when a bounded mouse or keyboard action fails."""


class ScreenControlError(RuntimeError):
    """Raised when a semantic screen action cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Result of an allowlisted local action."""

    action: str
    message: str
    target_url: str | None = None
    desktop_action: str | None = None


class DesktopAutomation(Protocol):
    """Execute only explicitly supported desktop commands."""

    def try_execute(self, command: str) -> ActionResult | None:
        """Execute a recognized safe command or return ``None``."""


class DesktopInput(Protocol):
    """Explicitly confirmed local mouse and keyboard operations."""

    def click(self, x: int, y: int) -> None:
        """Click one on-screen coordinate."""

    def type_text(self, text: str) -> None:
        """Type bounded text into the focused control."""

    def press(self, key: str) -> None:
        """Press one allowlisted key."""


class SemanticDesktopControl(Protocol):
    """Locate and operate visible controls from a fresh screen capture."""

    def click_text(self, label: str) -> None:
        """Find one unambiguous visible label and click its center."""

    def fill_field(self, label: str, value: str) -> None:
        """Find a visible field label, focus the nearby input, and type a value."""
