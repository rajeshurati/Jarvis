"""Fail-safe Windows mouse and keyboard input through PyAutoGUI."""

from __future__ import annotations

from typing import ClassVar

import pyautogui

from jarvis.capabilities.automation import DesktopInputError


class PyAutoGUIDesktopInput:
    """Perform atomic input actions with PyAutoGUI's corner fail-safe enabled."""

    _keys: ClassVar[set[str]] = {
        "enter", "tab", "escape", "backspace", "delete", "up", "down", "left", "right",
        "home", "end", "pageup", "pagedown", "space",
    }

    def __init__(self, pause_seconds: float = 0.15) -> None:
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = pause_seconds

    def click(self, x: int, y: int) -> None:
        """Click once only when coordinates are currently on-screen."""
        if x < 0 or y < 0 or not pyautogui.onScreen(x, y):
            raise DesktopInputError("Those click coordinates are outside the screen.")
        try:
            pyautogui.click(x=x, y=y)
        except Exception as error:
            raise DesktopInputError("The desktop click was stopped or failed.") from error

    def type_text(self, text: str) -> None:
        """Type printable text with a strict length bound."""
        if not text or len(text) > 500 or any(ord(character) < 32 for character in text):
            raise DesktopInputError("Typed text must contain 1 to 500 printable characters.")
        try:
            pyautogui.write(text, interval=0.01)
        except Exception as error:
            raise DesktopInputError("Desktop typing was stopped or failed.") from error

    def press(self, key: str) -> None:
        """Press one non-modifier key from the fixed allowlist."""
        normalized = key.casefold()
        if normalized not in self._keys:
            raise DesktopInputError("That keyboard key is not allowlisted.")
        try:
            pyautogui.press(normalized)
        except Exception as error:
            raise DesktopInputError("The key press was stopped or failed.") from error
