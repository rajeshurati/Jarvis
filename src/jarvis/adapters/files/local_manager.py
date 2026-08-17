"""Recoverable, bounded filesystem mutations in approved user folders."""

from __future__ import annotations

import shutil
from pathlib import Path

from send2trash import send2trash

from jarvis.capabilities.files import FileOperationError


class LocalFileManager:
    """Create, copy, move, and recycle without traversal or overwrites."""

    def __init__(self, roots: dict[str, Path]) -> None:
        self._roots = {
            name.casefold(): path.resolve() for name, path in roots.items() if path.is_dir()
        }

    def create_folder(self, root: str, name: str) -> Path:
        destination = self._destination(root, name)
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise FileOperationError("A file or folder with that name already exists.") from error
        except OSError as error:
            raise FileOperationError("The folder could not be created.") from error
        return destination

    def create_text_file(self, root: str, name: str, content: str) -> Path:
        if not content or len(content) > 10_000:
            raise FileOperationError("File content must contain 1 to 10000 characters.")
        destination = self._destination(root, name)
        try:
            with destination.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
        except FileExistsError as error:
            raise FileOperationError("A file with that name already exists.") from error
        except OSError as error:
            raise FileOperationError("The text file could not be created.") from error
        return destination

    def copy_to(self, source: Path, root: str) -> Path:
        validated = self._approved_existing(source)
        destination = self._destination(root, validated.name)
        try:
            if validated.is_dir():
                shutil.copytree(validated, destination)
            else:
                shutil.copy2(validated, destination)
        except FileExistsError as error:
            raise FileOperationError("The destination already contains that name.") from error
        except OSError as error:
            raise FileOperationError("The item could not be copied.") from error
        return destination

    def move_to(self, source: Path, root: str) -> Path:
        validated = self._approved_existing(source)
        destination = self._destination(root, validated.name)
        if destination.exists():
            raise FileOperationError("The destination already contains that name.")
        try:
            return Path(shutil.move(str(validated), str(destination)))
        except OSError as error:
            raise FileOperationError("The item could not be moved.") from error

    def recycle(self, source: Path) -> None:
        validated = self._approved_existing(source)
        try:
            send2trash(str(validated))
        except OSError as error:
            raise FileOperationError("The item could not be moved to the Recycle Bin.") from error

    def _destination(self, root: str, name: str) -> Path:
        base = self._roots.get(root.casefold())
        cleaned = name.strip().rstrip(". ")
        if base is None:
            raise FileOperationError("That destination folder is not approved.")
        unsafe = (
            not cleaned
            or len(cleaned) > 180
            or Path(cleaned).name != cleaned
            or cleaned in {".", ".."}
        )
        if unsafe:
            raise FileOperationError("That file or folder name is not safe.")
        return base / cleaned

    def _approved_existing(self, source: Path) -> Path:
        try:
            resolved = source.resolve(strict=True)
        except OSError as error:
            raise FileOperationError("The source item no longer exists.") from error
        if not any(resolved.is_relative_to(root) for root in self._roots.values()):
            raise FileOperationError("The source is outside approved user folders.")
        return resolved
