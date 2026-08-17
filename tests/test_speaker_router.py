"""Speaker voice-command routing tests."""

from jarvis.application.speaker_router import SpeakerCommandRouter
from jarvis.capabilities.automation import ActionResult
from jarvis.capabilities.identity import SpeakerResult


class StubDelegate:
    def try_execute(self, command: str) -> ActionResult | None:
        return ActionResult("delegated", command)


class StubSpeaker:
    def enroll_current(self, name: str) -> SpeakerResult:
        return SpeakerResult("enrolled", True, name, 1.0)

    def verify_current(self) -> SpeakerResult:
        return SpeakerResult("recognized", True, "Rajesh", 0.91)

    def delete_profile(self, name: str) -> bool:
        return name == "Rajesh"


def test_speaker_commands_and_confirmed_deletion() -> None:
    router = SpeakerCommandRouter(StubDelegate(), StubSpeaker())  # type: ignore[arg-type]

    enrolled = router.try_execute("enroll my voice")
    recognized = router.try_execute("who is speaking")
    pending = router.try_execute("delete speaker profile Rajesh")
    wrong = router.try_execute("confirm delete speaker profile Other")
    deleted = router.try_execute("confirm delete speaker profile Rajesh")

    assert enrolled and enrolled.action == "enroll_speaker"
    assert recognized and recognized.action == "recognize_speaker"
    assert pending and pending.action == "confirm_delete_speaker"
    assert wrong and wrong.action == "confirmation_missing"
    assert deleted and deleted.action == "delete_speaker"


def test_missing_speaker_model_is_truthful_and_other_commands_delegate() -> None:
    router = SpeakerCommandRouter(StubDelegate(), None)
    missing = router.try_execute("recognize my voice")
    delegated = router.try_execute("open calculator")

    assert missing and missing.action == "speaker_unavailable"
    assert delegated and delegated.action == "delegated"
