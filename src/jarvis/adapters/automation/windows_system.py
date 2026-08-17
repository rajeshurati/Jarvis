"""Bounded, reversible Windows system controls."""

from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from jarvis.capabilities.system import SystemControlError


def _open(command: list[str]) -> object:
    return subprocess.Popen(command, close_fds=True)


def _key(code: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(code, 0, 0, 0)
    user32.keybd_event(code, 0, 2, 0)


class WindowsSystemController:
    """Expose status, Settings pages, and non-destructive audio keys."""

    _settings: ClassVar[dict[str, str]] = {
        "sound": "ms-settings:sound",
        "microphone": "ms-settings:privacy-microphone",
        "display": "ms-settings:display",
        "network": "ms-settings:network-status",
        "bluetooth": "ms-settings:bluetooth",
        "power": "ms-settings:powersleep",
        "windows update": "ms-settings:windowsupdate",
    }
    _volume_keys: ClassVar[dict[str, int]] = {
        "up": 0xAF,
        "down": 0xAE,
        "mute": 0xAD,
    }

    def __init__(
        self,
        opener: Callable[[list[str]], object] = _open,
        key_sender: Callable[[int], None] = _key,
    ) -> None:
        self._opener = opener
        self._key_sender = key_sender

    def describe(self) -> str:
        """Return non-sensitive local device and storage status."""
        try:
            disk = shutil.disk_usage(Path.home().anchor)
        except OSError as error:
            raise SystemControlError("I could not read system storage status") from error
        free_gb = disk.free / (1024**3)
        total_gb = disk.total / (1024**3)
        return (
            f"Windows {platform.release()} on {platform.machine()}, "
            f"with {free_gb:.1f} of {total_gb:.1f} gigabytes free."
        )

    def open_settings(self, section: str) -> None:
        """Open one allowlisted Windows Settings page."""
        target = self._settings.get(section.casefold())
        if target is None:
            raise SystemControlError("That Settings page is not allowlisted")
        try:
            self._opener(["explorer.exe", target])
        except OSError as error:
            raise SystemControlError(f"I could not open {section} settings") from error

    def adjust_volume(self, operation: str) -> None:
        """Send one reversible hardware media-key event."""
        code = self._volume_keys.get(operation.casefold())
        if code is None:
            raise SystemControlError("That volume operation is not supported")
        try:
            self._key_sender(code)
        except OSError as error:
            raise SystemControlError("I could not change the volume") from error
