"""Voice recognition orchestration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.application.voice_service import VoiceRecognitionService
from jarvis.capabilities.speech import AudioDevice, Transcript


class FakeRecorder:
    """Deterministic recorder that creates no real microphone activity."""

    def __init__(self) -> None:
        self.recorded_path: Path | None = None

    def list_input_devices(self) -> list[AudioDevice]:
        return [AudioDevice(1, "Test microphone", 1, 16_000)]

    def record_wav(self, destination: Path, duration_seconds: float) -> Path:
        destination.write_bytes(b"test audio")
        self.recorded_path = destination
        return destination


class FakeTranscriber:
    """Deterministic local transcriber."""

    def transcribe(self, audio_path: Path) -> Transcript:
        assert audio_path.read_bytes() == b"test audio"
        return Transcript("Hello Jarvis", "en", 0.99, 1.25)


@pytest.mark.anyio
async def test_record_transcribe_and_delete_temporary_audio(tmp_path: Path) -> None:
    recorder = FakeRecorder()
    service = VoiceRecognitionService(
        recorder,
        FakeTranscriber(),
        max_recording_seconds=10,
        temporary_directory=tmp_path,
    )

    transcript = await service.record_and_transcribe(2)

    assert transcript.text == "Hello Jarvis"
    assert recorder.recorded_path is not None
    assert not recorder.recorded_path.exists()


@pytest.mark.anyio
async def test_duration_limit_is_enforced(tmp_path: Path) -> None:
    service = VoiceRecognitionService(
        FakeRecorder(),
        FakeTranscriber(),
        max_recording_seconds=5,
        temporary_directory=tmp_path,
    )

    with pytest.raises(ValueError, match="between 0 and 5"):
        await service.record_and_transcribe(6)


@pytest.mark.anyio
async def test_list_devices(tmp_path: Path) -> None:
    service = VoiceRecognitionService(
        FakeRecorder(),
        FakeTranscriber(),
        max_recording_seconds=5,
        temporary_directory=tmp_path,
    )

    devices = await service.list_input_devices()

    assert devices[0].name == "Test microphone"


@pytest.mark.anyio
async def test_uploaded_audio_is_transcribed_and_deleted(tmp_path: Path) -> None:
    service = VoiceRecognitionService(
        FakeRecorder(),
        FakeTranscriber(),
        max_recording_seconds=5,
        temporary_directory=tmp_path,
    )

    transcript = await service.transcribe_uploaded_audio(b"test audio", ".webm")

    assert transcript.text == "Hello Jarvis"
    assert list(tmp_path.iterdir()) == []
