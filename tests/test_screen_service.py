"""Transient screen-understanding tests."""

from jarvis.application.screen_service import ScreenUnderstandingService


class Capture:
    def capture_png(self) -> bytes:
        return b"png"


class Vision:
    def __init__(self) -> None:
        self.prompt = ""

    def describe(self, image: bytes, prompt: str) -> str:
        assert image == b"png"
        self.prompt = prompt
        return "A browser is visible."


class VerboseVision:
    def describe(self, image: bytes, prompt: str) -> str:
        return "visible " * 300


class InitiallyReluctantVision:
    def __init__(self) -> None:
        self.calls = 0

    def describe(self, image: bytes, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "I cannot access the screen."
        return "The Jarvis page is visible, but not seeing your monitor yet — a browser is open."


def test_screen_is_captured_and_prompted_without_storage() -> None:
    vision = Vision()
    service = ScreenUnderstandingService(Capture(), vision)

    assert service.describe("read my screen") == "A browser is visible."
    assert "read my screen" in vision.prompt
    assert "specific visible text" in vision.prompt


def test_general_screen_question_does_not_recite_chat() -> None:
    vision = Vision()
    ScreenUnderstandingService(Capture(), vision).describe("what is on my screen")
    assert "Do not quote or summarize chat-message bodies" in vision.prompt


def test_verbose_visual_answer_is_bounded_for_speech() -> None:
    result = ScreenUnderstandingService(Capture(), VerboseVision()).describe("look")
    assert len(result) <= 1_203
    assert result.endswith("...")


def test_false_access_refusal_is_retried_with_visual_facts() -> None:
    vision = InitiallyReluctantVision()
    result = ScreenUnderstandingService(Capture(), vision).describe("what is visible")
    assert vision.calls == 2
    assert "Jarvis page" in result
    assert "not seeing" not in result
