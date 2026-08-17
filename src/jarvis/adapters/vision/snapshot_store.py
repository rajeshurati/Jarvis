"""Short-lived in-memory screen snapshots from the interactive desktop process."""

from __future__ import annotations

import threading
import time
from typing import Protocol

from jarvis.capabilities.vision import ScreenCaptureError


class _ScreenSource(Protocol):
    def capture_png(self) -> bytes: ...
    def capture_png_with_origin(self) -> tuple[bytes, int, int]: ...


class InMemoryScreenSnapshotStore:
    """Hold only the newest PNG in memory and reject stale desktop state."""

    def __init__(self, maximum_age_seconds: float = 10.0) -> None:
        self._maximum_age = maximum_age_seconds
        self._lock = threading.Lock()
        self._snapshot: tuple[bytes, int, int, float] | None = None

    def update(self, image: bytes, left: int = 0, top: int = 0) -> None:
        """Replace the transient snapshot after strict PNG and size validation."""
        if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 20_000_000:
            raise ValueError("Screen snapshot must be a PNG smaller than 20 MB")
        with self._lock:
            self._snapshot = (bytes(image), left, top, time.monotonic())

    def capture_png(self) -> bytes:
        image, _, _ = self.capture_png_with_origin()
        return image

    def capture_png_with_origin(self) -> tuple[bytes, int, int]:
        """Return a fresh snapshot without persisting it."""
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None or time.monotonic() - snapshot[3] > self._maximum_age:
            raise ScreenCaptureError("The interactive screen snapshot is unavailable or stale.")
        return snapshot[0], snapshot[1], snapshot[2]

    def status(self) -> tuple[bool, float | None]:
        """Return availability and age without exposing image data."""
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            return False, None
        age = max(0.0, time.monotonic() - snapshot[3])
        return age <= self._maximum_age, age


class FallbackScreenCapturer:
    """Prefer direct capture, then use the interactive short-lived snapshot."""

    def __init__(
        self, primary: _ScreenSource, fallback: InMemoryScreenSnapshotStore
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def capture_png(self) -> bytes:
        try:
            return self._primary.capture_png()
        except ScreenCaptureError:
            return self._fallback.capture_png()

    def capture_png_with_origin(self) -> tuple[bytes, int, int]:
        try:
            return self._primary.capture_png_with_origin()
        except ScreenCaptureError:
            return self._fallback.capture_png_with_origin()
