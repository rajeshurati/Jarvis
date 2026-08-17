"""Voice-command boundary for optional local speaker recognition."""

from __future__ import annotations

import re

from jarvis.application.speaker_service import SpeakerRecognitionService
from jarvis.capabilities.automation import ActionResult, DesktopAutomation
from jarvis.capabilities.identity import IdentityError


class SpeakerCommandRouter:
    """Intercept speaker commands and delegate every other typed capability."""

    def __init__(
        self,
        delegate: DesktopAutomation,
        speaker: SpeakerRecognitionService | None,
    ) -> None:
        self._delegate = delegate
        self._speaker = speaker
        self._pending_delete: str | None = None

    def try_execute(self, command: str) -> ActionResult | None:
        normalized = re.sub(r"\s+", " ", command.strip()).rstrip(".!?")
        lowered = normalized.casefold()
        if lowered in {"enroll my voice", "register my voice", "enroll speaker"}:
            if self._speaker is None:
                return ActionResult(
                    "speaker_unavailable",
                    "Local speaker recognition needs ONNX speaker weights installed first.",
                )
            try:
                result = self._speaker.enroll_current("Rajesh")
            except IdentityError as error:
                return ActionResult("speaker_error", str(error))
            return ActionResult(
                "enroll_speaker", f"Local voice recognition is enrolled for {result.name}."
            )

        if lowered in {"recognize my voice", "who is speaking", "verify speaker"}:
            if self._speaker is None:
                return ActionResult(
                    "speaker_unavailable",
                    "Local speaker recognition needs ONNX speaker weights installed first.",
                )
            try:
                result = self._speaker.verify_current()
            except IdentityError as error:
                return ActionResult("speaker_error", str(error))
            if result.recognized:
                return ActionResult(
                    "recognize_speaker",
                    f"Voice recognized as {result.name}, similarity {result.similarity:.2f}. "
                    "Voice alone does not authorize sensitive actions.",
                )
            return ActionResult("recognize_speaker", "The current voice is not recognized.")

        confirm = re.fullmatch(r"confirm delete speaker profile (.+)", normalized, re.I)
        if confirm:
            profile_name: str = confirm.group(1).strip()
            if self._speaker is None or self._pending_delete != profile_name:
                return ActionResult("confirmation_missing", "That deletion is not pending.")
            self._pending_delete = None
            deleted = self._speaker.delete_profile(profile_name)
            return ActionResult(
                "delete_speaker",
                "Speaker profile deleted." if deleted else "Speaker profile not found.",
            )
        deletion = re.fullmatch(r"delete speaker profile (.+)", normalized, re.I)
        if deletion:
            name = deletion.group(1).strip()
            self._pending_delete = name
            return ActionResult(
                "confirm_delete_speaker",
                f"This removes the local voiceprint for {name}. "
                f"Say confirm delete speaker profile {name}.",
            )
        return self._delegate.try_execute(command)
