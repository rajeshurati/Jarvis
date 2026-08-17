"""Fresh-screen semantic desktop controls backed by local OCR."""

from __future__ import annotations

from jarvis.capabilities.automation import DesktopInput, ScreenControlError
from jarvis.capabilities.documents import DocumentError
from jarvis.capabilities.vision import (
    PositionedScreenCapturer,
    ScreenCaptureError,
    ScreenTextLocator,
    ScreenTextRegion,
)


class SemanticDesktopService:
    """Resolve visible labels immediately before a confirmed desktop action."""

    def __init__(
        self,
        capturer: PositionedScreenCapturer,
        locator: ScreenTextLocator,
        desktop_input: DesktopInput,
    ) -> None:
        self._capturer = capturer
        self._locator = locator
        self._input = desktop_input

    def _find_one(self, label: str) -> tuple[ScreenTextRegion, int, int]:
        clean_label = " ".join(label.split()).strip()
        if not clean_label or len(clean_label) > 200:
            raise ScreenControlError("The visible label must contain 1 to 200 characters.")
        try:
            image, origin_x, origin_y = self._capturer.capture_png_with_origin()
            matches = self._locator.locate(image, clean_label)
        except (ScreenCaptureError, DocumentError) as error:
            raise ScreenControlError(str(error)) from error
        if not matches:
            raise ScreenControlError(f'I cannot find visible text matching "{clean_label}".')
        best = matches[0]
        if len(matches) > 1 and self._is_ambiguous(best, matches[1]):
            raise ScreenControlError(
                f'I found multiple visible matches for "{clean_label}". Use a more specific label.'
            )
        return best, origin_x, origin_y

    @staticmethod
    def _is_ambiguous(first: ScreenTextRegion, second: ScreenTextRegion) -> bool:
        first_text = " ".join(first.text.casefold().split())
        second_text = " ".join(second.text.casefold().split())
        return first_text == second_text and abs(first.confidence - second.confidence) < 0.10

    def click_text(self, label: str) -> None:
        """Click the center of one unambiguous OCR label."""
        region, origin_x, origin_y = self._find_one(label)
        self._input.click(
            origin_x + (region.left + region.right) // 2,
            origin_y + (region.top + region.bottom) // 2,
        )

    def fill_field(self, label: str, value: str) -> None:
        """Focus a control immediately to the right of its label and type text."""
        if not 1 <= len(value) <= 500 or not value.isprintable():
            raise ScreenControlError("Field text must contain 1 to 500 printable characters.")
        region, origin_x, origin_y = self._find_one(label)
        field_x = origin_x + region.right + max(40, min(160, region.right - region.left))
        field_y = origin_y + (region.top + region.bottom) // 2
        self._input.click(field_x, field_y)
        self._input.type_text(value)
