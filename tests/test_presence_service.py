"""Continuous room-presence monitoring tests."""

from pathlib import Path

import pytest

from jarvis.adapters.memory.sqlite_store import SQLiteMemoryStore
from jarvis.application.presence_service import PresenceMonitorService
from jarvis.capabilities.identity import IdentityError


class SequenceIdentity:
    def __init__(self, faces: list[int | Exception]) -> None:
        self.faces = iter(faces)

    def faces_current(self) -> int:
        value = next(self.faces)
        if isinstance(value, Exception):
            raise value
        return value


def store(tmp_path: Path) -> SQLiteMemoryStore:
    memory = SQLiteMemoryStore(tmp_path / "jarvis.db")
    memory.initialize()
    return memory


@pytest.mark.anyio
async def test_presence_records_only_transitions(tmp_path: Path) -> None:
    memory = store(tmp_path)
    monitor = PresenceMonitorService(
        SequenceIdentity([0, 0, 1, 2, 0]),  # type: ignore[arg-type]
        memory,
        interval_seconds=2,
    )

    for _ in range(5):
        await monitor.sample()

    events = list(reversed(memory.list_presence_events()))
    assert [(item.state, item.faces) for item in events] == [
        ("vacant", 0),
        ("entered", 1),
        ("left", 0),
    ]
    assert "left" in monitor.summary()


@pytest.mark.anyio
async def test_presence_recovers_from_camera_error(tmp_path: Path) -> None:
    memory = store(tmp_path)
    monitor = PresenceMonitorService(
        SequenceIdentity([IdentityError("camera"), 1]),  # type: ignore[arg-type]
        memory,
        interval_seconds=2,
    )

    assert await monitor.sample() is None
    assert monitor.last_error is not None
    event = await monitor.sample()
    assert event and event.state == "present"
    assert monitor.last_error is None


@pytest.mark.anyio
async def test_presence_background_task_starts_and_stops(tmp_path: Path) -> None:
    monitor = PresenceMonitorService(
        SequenceIdentity([0]),  # type: ignore[arg-type]
        store(tmp_path),
        interval_seconds=2,
        enabled=False,
    )
    await monitor.start()
    await monitor.start()
    monitor.enable()
    assert monitor.enabled is True
    monitor.disable()
    assert monitor.enabled is False
    await monitor.stop()
