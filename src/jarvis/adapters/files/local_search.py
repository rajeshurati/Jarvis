"""Bounded filename search in approved user folders."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar


class LocalFileSearch:
    """Search filenames without opening or indexing personal documents."""

    _ignored: ClassVar[set[str]] = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        "AppData",
    }

    def __init__(self, roots: list[Path]) -> None:
        self._roots = [root.resolve() for root in roots if root.is_dir()]

    def find(self, query: str, limit: int = 10) -> list[Path]:
        """Find paths whose names contain every query word."""
        words = [word.casefold() for word in query.split() if word.strip()]
        if not words:
            return []
        matches: list[Path] = []
        for root in self._roots:
            for directory, folders, files in os.walk(root, topdown=True, onerror=lambda _: None):
                folders[:] = [folder for folder in folders if folder not in self._ignored]
                for name in [*folders, *files]:
                    folded = name.casefold()
                    if all(word in folded for word in words):
                        matches.append(Path(directory) / name)
                        if len(matches) >= limit:
                            return matches
        return matches
