"""Local document and OCR contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DocumentError(RuntimeError):
    """Raised when a requested local document cannot be processed safely."""


class DocumentReader(Protocol):
    """Extract bounded text from a supported local document."""

    def read(self, path: Path) -> str:
        """Return plain text without modifying the source file."""


class OpticalCharacterRecognizer(Protocol):
    """Extract text from an image locally."""

    def read(self, path: Path) -> str:
        """Return recognized text in reading order."""
