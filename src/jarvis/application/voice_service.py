"""Voice recognition application service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

from jarvis.capabilities.speech import AudioDevice, AudioRecorder, SpeechTranscriber, Transcript


class VoiceRecognitionService:
    """Coordinate recording and transcription while cleaning temporary audio."""

    def __init__(
        self,
        recorder: AudioRecorder,
        transcriber: SpeechTranscriber,
        *,
        max_recording_seconds: float,
        temporary_directory: Path,
    ) -> None:
        self._recorder = recorder
        self._transcriber = transcriber
        self._max_recording_seconds = max_recording_seconds
        self._temporary_directory = temporary_directory
        self._operation_lock = asyncio.Lock()

    async def list_input_devices(self) -> list[AudioDevice]:
        """Enumerate devices without blocking the API event loop."""
        return await asyncio.to_thread(self._recorder.list_input_devices)

    async def record_and_transcribe(self, duration_seconds: float) -> Transcript:
        """Record one utterance, transcribe it locally, then delete raw audio."""
        if not 0 < duration_seconds <= self._max_recording_seconds:
            raise ValueError(
                f"duration_seconds must be between 0 and {self._max_recording_seconds}"
            )
        self._temporary_directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=".wav",
            dir=self._temporary_directory,
            delete=False,
        ) as temporary_file:
            audio_path = Path(temporary_file.name)

        async with self._operation_lock:
            try:
                await asyncio.to_thread(
                    self._recorder.record_wav,
                    audio_path,
                    duration_seconds,
                )
                return await asyncio.to_thread(self._transcriber.transcribe, audio_path)
            finally:
                audio_path.unlink(missing_ok=True)

    async def transcribe_uploaded_audio(self, content: bytes, suffix: str) -> Transcript:
        """Transcribe bounded browser-captured audio and delete it afterward."""
        if not content:
            raise ValueError("Uploaded audio is empty")
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("Uploaded audio exceeds the 25 MB local limit")
        safe_suffix = suffix if suffix in {".webm", ".wav", ".ogg", ".mp4"} else ".webm"
        self._temporary_directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=safe_suffix,
            dir=self._temporary_directory,
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            audio_path = Path(temporary_file.name)
        async with self._operation_lock:
            try:
                return await asyncio.to_thread(self._transcriber.transcribe, audio_path)
            finally:
                audio_path.unlink(missing_ok=True)
