"""Transient interactive webcam cache tests."""

from jarvis.adapters.identity.camera_snapshot_store import (
    FallbackCamera,
    InMemoryCameraSnapshotStore,
)
from jarvis.capabilities.identity import IdentityError

JPEG = b"\xff\xd8\xff" + b"test"


class BlockedCamera:
    def capture_jpeg(self) -> bytes:
        raise IdentityError("blocked")


class TrackingCamera:
    def __init__(self) -> None:
        self.calls = 0

    def capture_jpeg(self) -> bytes:
        self.calls += 1
        return b"\xff\xd8\xffprimary"


def test_interactive_frame_is_used_when_background_camera_is_blocked() -> None:
    store = InMemoryCameraSnapshotStore()
    store.update(JPEG)
    camera = FallbackCamera(BlockedCamera(), store)

    assert camera.capture_jpeg() == JPEG
    assert store.status()[0] is True


def test_fresh_interactive_frame_avoids_opening_background_camera() -> None:
    store = InMemoryCameraSnapshotStore()
    store.update(JPEG)
    primary = TrackingCamera()
    camera = FallbackCamera(primary, store)

    assert camera.capture_jpeg() == JPEG
    assert primary.calls == 0


def test_direct_camera_is_used_when_no_interactive_frame_exists() -> None:
    primary = TrackingCamera()
    camera = FallbackCamera(primary, InMemoryCameraSnapshotStore())

    assert camera.capture_jpeg() == b"\xff\xd8\xffprimary"
    assert primary.calls == 1


def test_clear_discards_transient_interactive_frame() -> None:
    store = InMemoryCameraSnapshotStore()
    store.update(JPEG)

    store.clear()

    assert store.status() == (False, None)
