"""Bounded local filesystem mutation tests."""

from pathlib import Path

import pytest

from jarvis.adapters.files.local_manager import LocalFileManager
from jarvis.capabilities.files import FileOperationError


@pytest.fixture
def manager(tmp_path: Path) -> LocalFileManager:
    return LocalFileManager({"downloads": tmp_path})


def test_create_copy_and_move_without_overwriting(
    manager: LocalFileManager, tmp_path: Path
) -> None:
    folder = manager.create_folder("downloads", "Jarvis Work")
    created = manager.create_text_file("downloads", "note.txt", "hello")
    nested = folder / "nested.txt"
    nested.write_text("copy me", encoding="utf-8")
    copied = manager.copy_to(nested, "downloads")

    assert folder.is_dir()
    assert copied.read_text(encoding="utf-8") == "copy me"
    assert created.name == "note.txt"
    with pytest.raises(FileOperationError, match="already exists"):
        manager.create_text_file("downloads", "note.txt", "overwrite")


def test_move_between_approved_roots(tmp_path: Path) -> None:
    source_root, target_root = tmp_path / "source", tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()
    source = source_root / "move.txt"
    source.write_text("move", encoding="utf-8")
    manager = LocalFileManager({"desktop": source_root, "downloads": target_root})

    moved = manager.move_to(source, "downloads")
    assert moved == target_root / "move.txt"
    assert moved.read_text(encoding="utf-8") == "move"


def test_traversal_and_unapproved_sources_are_rejected(
    manager: LocalFileManager, tmp_path: Path
) -> None:
    with pytest.raises(FileOperationError, match="not safe"):
        manager.create_folder("downloads", "../escape")
    outside = tmp_path.parent / "outside-jarvis-test.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        with pytest.raises(FileOperationError, match="outside approved"):
            manager.copy_to(outside, "downloads")
    finally:
        outside.unlink(missing_ok=True)


def test_recycle_uses_recoverable_os_trash(
    manager: LocalFileManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = tmp_path / "recycle.txt"
    item.write_text("recoverable", encoding="utf-8")
    recycled: list[str] = []
    monkeypatch.setattr("jarvis.adapters.files.local_manager.send2trash", recycled.append)

    manager.recycle(item)
    assert recycled == [str(item)]
