"""Speech capability contracts and domain values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SpeechError(RuntimeError):
    """Base error for expected speech capability failures."""


class AudioDeviceError(SpeechError):
    """Raised when audio hardware is unavailable or cannot be opened."""


class ModelUnavailableError(SpeechError):
    """Raised when the local speech model is missing or cannot load."""


class TranscriptionError(SpeechError):
    """Raised when valid audio cannot be transcribed."""


@dataclass(frozen=True, slots=True)
class AudioDevice:
    """A microphone exposed by the operating system."""

    index: int
    name: str
    input_channels: int
    default_sample_rate: float


@dataclass(frozen=True, slots=True)
class Transcript:
    """Normalized local speech-recognition result."""

    text: str
    language: str
    language_probability: float
    duration_seconds: float


class AudioRecorder(Protocol):
    """Capture microphone audio into a standard WAV file."""

    def list_input_devices(self) -> list[AudioDevice]:
        """Return usable microphone devices."""

    def record_wav(self, destination: Path, duration_seconds: float) -> Path:
        """Record a fixed-duration WAV file."""


class SpeechTranscriber(Protocol):
    """Convert an audio file into text without exposing its contents."""

    def transcribe(self, audio_path: Path) -> Transcript:
        """Transcribe one local audio file."""


class WakeWordDetector(Protocol):
    """Detect a wake phrase in streaming 16 kHz mono PCM."""

    def reset(self) -> None:
        """Reset streaming model state for a new session."""

    def process_pcm(self, pcm: bytes) -> tuple[bool, float]:
        """Process little-endian signed 16-bit PCM and return detection state."""


class SpeechSynthesizer(Protocol):
    """Convert assistant text to a local WAV file."""

    def synthesize_wav(self, text: str, destination: Path) -> Path:
        """Render one utterance without using a cloud service."""
