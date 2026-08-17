"""Semantic screen-control tests."""

import pytest

from jarvis.application.semantic_desktop_service import SemanticDesktopService
from jarvis.capabilities.automation import ScreenControlError
from jarvis.capabilities.vision import ScreenTextRegion


class StubCapture:
    def capture_png_with_origin(self) -> tuple[bytes, int, int]:
        return b"png", -100, 10


class StubLocator:
    def __init__(self, matches: list[ScreenTextRegion]) -> None:
        self.matches = matches
        self.calls: list[tuple[bytes, str]] = []

    def locate(self, image: bytes, query: str) -> list[ScreenTextRegion]:
        self.calls.append((image, query))
        return self.matches


class StubInput:
    def __init__(self) -> None:
        self.actions: list[tuple[object, ...]] = []

    def click(self, x: int, y: int) -> None:
        self.actions.append(("click", x, y))

    def type_text(self, text: str) -> None:
        self.actions.append(("type", text))

    def press(self, key: str) -> None:
        self.actions.append(("press", key))


def region(text: str = "Submit", confidence: float = 0.95) -> ScreenTextRegion:
    return ScreenTextRegion(text, confidence, 200, 100, 300, 140)


def test_click_uses_fresh_capture_and_virtual_desktop_origin() -> None:
    locator = StubLocator([region()])
    desktop_input = StubInput()
    service = SemanticDesktopService(StubCapture(), locator, desktop_input)

    service.click_text("Submit")

    assert locator.calls == [(b"png", "Submit")]
    assert desktop_input.actions == [("click", 150, 130)]


def test_missing_or_ambiguous_visible_labels_are_rejected() -> None:
    desktop_input = StubInput()
    missing = SemanticDesktopService(StubCapture(), StubLocator([]), desktop_input)
    ambiguous = SemanticDesktopService(
        StubCapture(), StubLocator([region(), region(confidence=0.91)]), desktop_input
    )

    with pytest.raises(ScreenControlError, match="cannot find"):
        missing.click_text("Save")
    with pytest.raises(ScreenControlError, match="multiple"):
        ambiguous.click_text("Submit")
    assert desktop_input.actions == []


def test_fill_field_focuses_near_label_then_types() -> None:
    desktop_input = StubInput()
    service = SemanticDesktopService(StubCapture(), StubLocator([region("Email")]), desktop_input)

    service.fill_field("Email", "rajesh@example.com")

    assert desktop_input.actions == [
        ("click", 300, 130),
        ("type", "rajesh@example.com"),
    ]


def test_fill_field_rejects_non_printable_or_oversized_text() -> None:
    service = SemanticDesktopService(StubCapture(), StubLocator([region()]), StubInput())
    with pytest.raises(ScreenControlError, match="printable"):
        service.fill_field("Name", "bad\ntext")
    with pytest.raises(ScreenControlError, match="500"):
        service.fill_field("Name", "x" * 501)
