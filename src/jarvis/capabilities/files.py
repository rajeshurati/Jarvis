"""Read-only local file-search contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileSearch(Protocol):
    """Search approved user folders without reading file contents."""

    def find(self, query: str, limit: int = 10) -> list[Path]:
        """Return matching paths."""


class FileOperationError(RuntimeError):
    """Raised when a bounded local filesystem operation is unsafe or fails."""


class FileManager(Protocol):
    """Confirmed mutations limited to approved user folders."""

    def create_folder(self, root: str, name: str) -> Path: ...

    def create_text_file(self, root: str, name: str, content: str) -> Path: ...

    def copy_to(self, source: Path, root: str) -> Path: ...

    def move_to(self, source: Path, root: str) -> Path: ...

    def recycle(self, source: Path) -> None: ...
