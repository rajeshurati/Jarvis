"""Local face-authorization contracts and values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class IdentityError(RuntimeError):
    """Raised when local biometric processing cannot complete safely."""


@dataclass(frozen=True, slots=True)
class IdentityResult:
    """One enrollment or authorization decision."""

    status: str
    authorized: bool
    name: str | None
    similarity: float | None
    faces_detected: int


@dataclass(frozen=True, slots=True)
class SpeakerResult:
    """One local voice enrollment or recognition result."""

    status: str
    recognized: bool
    name: str | None
    similarity: float | None


class FaceEmbeddingEngine(Protocol):
    """Convert a transient image into normalized face embeddings."""

    def extract(self, image: bytes) -> list[list[float]]:
        """Return one embedding for every detected face."""


class FaceProfileStore(Protocol):
    """Persist only derived face embeddings, never raw photos."""

    def profiles(self) -> dict[str, list[list[float]]]:
        """Return a copy of all enrolled profiles."""

    def add_sample(self, name: str, embedding: list[float]) -> None:
        """Add a bounded enrollment sample."""

    def delete(self, name: str) -> bool:
        """Delete one profile and all its samples."""


class Camera(Protocol):
    """Capture one transient local webcam frame."""

    def capture_jpeg(self) -> bytes:
        """Return a JPEG without writing it to disk."""


class SpeakerEmbeddingEngine(Protocol):
    """Convert a local WAV sample into one normalized speaker embedding."""

    def extract(self, audio_path: Path) -> list[float]:
        """Return one normalized voiceprint."""


class SpeakerProfileStore(Protocol):
    """Persist derived voiceprints without retaining raw audio."""

    def profiles(self) -> dict[str, list[list[float]]]:
        """Return an isolated copy of enrolled voiceprints."""

    def add_sample(self, name: str, embedding: list[float]) -> None:
        """Add one bounded enrollment sample."""

    def delete(self, name: str) -> bool:
        """Delete one speaker profile."""
