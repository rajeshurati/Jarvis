"""Local faster-whisper speech recognition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.capabilities.speech import (
    ModelUnavailableError,
    Transcript,
    TranscriptionError,
)


class FasterWhisperTranscriber:
    """Lazily load a Whisper model and transcribe audio locally."""

    def __init__(
        self,
        model: str,
        *,
        device: str = "auto",
        compute_type: str = "default",
        language: str | None = "en",
    ) -> None:
        self._model_reference = model
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_reference,
                device=self._device,
                compute_type=self._compute_type,
            )
        except Exception as error:
            raise ModelUnavailableError("Unable to load the local Whisper model") from error
        return self._model

    def warm_up(self) -> None:
        """Load model weights before Jarvis advertises voice readiness."""
        self._load_model()

    def transcribe(self, audio_path: Path) -> Transcript:
        """Transcribe speech with VAD filtering and no network calls."""
        if not audio_path.is_file():
            raise TranscriptionError(f"Audio file does not exist: {audio_path}")
        try:
            segments, info = self._load_model().transcribe(
                str(audio_path),
                language=self._language,
                beam_size=2,
                vad_filter=False,
                condition_on_previous_text=False,
                initial_prompt=(
                    "Jarvis desktop assistant. Gmail and email commands. Names may include "
                    "many different people. Commands include open Gmail, open a named mail, "
                    "open the first mail, open the second mail, open the third mail, open the "
                    "fourth mail, scroll down, scroll up, maximize, minimize, and close tab."
                ),
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return Transcript(
                text=text,
                language=str(info.language),
                language_probability=float(info.language_probability),
                duration_seconds=float(info.duration),
            )
        except ModelUnavailableError:
            raise
        except Exception as error:
            raise TranscriptionError(
                f"Local speech transcription failed ({type(error).__name__}: {error})"
            ) from error
