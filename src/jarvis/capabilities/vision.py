"""Local screen-understanding contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ScreenCaptureError(RuntimeError):
    """Raised when Windows does not provide a screen image."""


class ScreenCapturer(Protocol):
    """Capture the current desktop without saving it permanently."""

    def capture_png(self) -> bytes:
        """Return a PNG of the current virtual desktop."""


class PositionedScreenCapturer(Protocol):
    """Capture a virtual desktop together with its global coordinate origin."""

    def capture_png_with_origin(self) -> tuple[bytes, int, int]:
        """Return PNG bytes plus the virtual desktop's left and top coordinates."""


@dataclass(frozen=True, slots=True)
class ScreenTextRegion:
    """One OCR text box expressed in capture-relative coordinates."""

    text: str
    confidence: float
    left: int
    top: int
    right: int
    bottom: int


class ScreenTextLocator(Protocol):
    """Find visible text regions in an in-memory screen image."""

    def locate(self, image: bytes, query: str) -> list[ScreenTextRegion]:
        """Return candidate regions ordered from strongest to weakest match."""


class VisionModel(Protocol):
    """Interpret a local image without sending it to a cloud service."""

    def describe(self, image: bytes, prompt: str) -> str:
        """Return a concise visual answer."""


@dataclass(frozen=True, slots=True)
class DetectedObject:
    """One locally detected webcam object."""

    label: str
    confidence: float
    left: int
    top: int
    right: int
    bottom: int


class ObjectDetector(Protocol):
    """Run bounded local object detection on an in-memory image."""

    def detect(self, image: bytes) -> list[DetectedObject]:
        """Return confident detections without retaining the image."""
