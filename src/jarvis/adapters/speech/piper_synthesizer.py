"""Piper neural text-to-speech adapter."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from jarvis.capabilities.speech import SpeechError


class PiperSynthesizer:
    """Lazily load one local Piper voice and render WAV speech."""

    def __init__(self, model_path: Path) -> None:
        self._model_path = model_path
        self._voice: Any | None = None

    def _load_voice(self) -> Any:
        if self._voice is not None:
            return self._voice
        try:
            from piper import PiperVoice

            self._voice = PiperVoice.load(str(self._model_path))
        except Exception as error:
            raise SpeechError("Unable to load the local Piper voice") from error
        return self._voice

    def synthesize_wav(self, text: str, destination: Path) -> Path:
        """Render one bounded utterance to a standard WAV file."""
        if not text.strip() or len(text) > 2_000:
            raise ValueError("Speech text must contain between 1 and 2000 characters")
        try:
            with wave.open(str(destination), "wb") as wav_file:
                self._load_voice().synthesize_wav(text, wav_file)
        except (OSError, RuntimeError, ValueError) as error:
            raise SpeechError("Local Piper speech synthesis failed") from error
        if destination.stat().st_size <= 44:
            raise SpeechError("Local Piper speech synthesis produced no audio")
        return destination
