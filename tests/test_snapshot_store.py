"""Transient interactive screen cache tests."""

from jarvis.adapters.vision.snapshot_store import (
    FallbackScreenCapturer,
    InMemoryScreenSnapshotStore,
)
from jarvis.capabilities.vision import ScreenCaptureError

PNG = b"\x89PNG\r\n\x1a\n" + b"test"


class BlockedCapture:
    def capture_png(self) -> bytes:
        raise ScreenCaptureError("blocked")

    def capture_png_with_origin(self) -> tuple[bytes, int, int]:
        raise ScreenCaptureError("blocked")


def test_interactive_snapshot_is_used_when_background_capture_is_blocked() -> None:
    store = InMemoryScreenSnapshotStore()
    store.update(PNG, -100, 20)
    capture = FallbackScreenCapturer(BlockedCapture(), store)

    assert capture.capture_png() == PNG
    assert capture.capture_png_with_origin() == (PNG, -100, 20)
    assert store.status()[0] is True
