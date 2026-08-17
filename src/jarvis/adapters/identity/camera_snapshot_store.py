"""Short-lived in-memory webcam frames from the interactive desktop process."""

from __future__ import annotations

import threading
import time
from typing import Protocol

from jarvis.capabilities.identity import IdentityError


class _CameraSource(Protocol):
    def capture_jpeg(self) -> bytes: ...


class InMemoryCameraSnapshotStore:
    """Hold only the newest JPEG and reject stale room state."""

    def __init__(self, maximum_age_seconds: float = 20.0) -> None:
        self._maximum_age = maximum_age_seconds
        self._lock = threading.Lock()
        self._snapshot: tuple[bytes, float] | None = None

    def update(self, image: bytes) -> None:
        if not image.startswith(b"\xff\xd8\xff") or len(image) > 10_000_000:
            raise ValueError("Camera snapshot must be a JPEG smaller than 10 MB")
        with self._lock:
            self._snapshot = (bytes(image), time.monotonic())

    def capture_jpeg(self) -> bytes:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None or time.monotonic() - snapshot[1] > self._maximum_age:
            raise IdentityError("The interactive webcam snapshot is unavailable or stale.")
        return snapshot[0]

    def status(self) -> tuple[bool, float | None]:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            return False, None
        age = max(0.0, time.monotonic() - snapshot[1])
        return age <= self._maximum_age, age

    def clear(self) -> None:
        """Discard the transient frame immediately when camera use is disabled."""
        with self._lock:
            self._snapshot = None


class FallbackCamera:
    """Prefer the interactive snapshot, then attempt one direct capture.

    The signed-in desktop publisher owns a continuous camera session while room
    monitoring is active.  Trying the background OpenCV device first would open
    and release a second session for every sample, which makes the privacy light
    flash and can disrupt the interactive stream.
    """

    def __init__(self, primary: _CameraSource, fallback: InMemoryCameraSnapshotStore) -> None:
        self._primary = primary
        self._fallback = fallback

    def capture_jpeg(self) -> bytes:
        try:
            return self._fallback.capture_jpeg()
        except IdentityError:
            return self._primary.capture_jpeg()
