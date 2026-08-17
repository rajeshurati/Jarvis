"""Local speaker enrollment and recognition tests."""

from pathlib import Path

from jarvis.adapters.identity.voice_profiles import JsonSpeakerProfileStore
from jarvis.application.speaker_service import SpeakerRecognitionService


class StubRecorder:
    def __init__(self) -> None:
        self.recordings: list[Path] = []

    def list_input_devices(self) -> list[object]:
        return []

    def record_wav(self, destination: Path, duration_seconds: float) -> Path:
        destination.write_bytes(b"temporary voice")
        self.recordings.append(destination)
        return destination


class SequenceEngine:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = iter(embeddings)

    def extract(self, audio_path: Path) -> list[float]:
        assert audio_path.is_file()
        return next(self.embeddings)


def test_speaker_enrollment_recognition_and_audio_cleanup(tmp_path: Path) -> None:
    recorder = StubRecorder()
    profiles = JsonSpeakerProfileStore(tmp_path / "speakers.json")
    service = SpeakerRecognitionService(
        SequenceEngine([[1.0, 0.0], [0.98, 0.02]]),  # type: ignore[arg-type]
        profiles,
        recorder,  # type: ignore[arg-type]
        tmp_path / "audio",
        threshold=0.8,
    )

    enrolled = service.enroll_current("Rajesh")
    recognized = service.verify_current()

    assert enrolled.status == "enrolled"
    assert recognized.recognized is True and recognized.name == "Rajesh"
    assert service.profile_names() == ["Rajesh"]
    assert all(not path.exists() for path in recorder.recordings)
    assert service.delete_profile("Rajesh") is True


def test_unenrolled_speaker_does_not_open_microphone(tmp_path: Path) -> None:
    recorder = StubRecorder()
    service = SpeakerRecognitionService(
        SequenceEngine([]),  # type: ignore[arg-type]
        JsonSpeakerProfileStore(tmp_path / "speakers.json"),
        recorder,  # type: ignore[arg-type]
        tmp_path / "audio",
    )

    result = service.verify_current()

    assert result.status == "not_enrolled"
    assert recorder.recordings == []


def test_unrecognized_voice_does_not_reveal_closest_profile(tmp_path: Path) -> None:
    profiles = JsonSpeakerProfileStore(tmp_path / "speakers.json")
    profiles.add_sample("Rajesh", [1.0, 0.0])
    service = SpeakerRecognitionService(
        SequenceEngine([[0.0, 1.0]]),  # type: ignore[arg-type]
        profiles,
        StubRecorder(),  # type: ignore[arg-type]
        tmp_path / "audio",
        threshold=0.8,
    )

    result = service.verify_current()

    assert result.status == "unrecognized"
    assert result.name is None


def test_interactive_uploaded_audio_is_enrolled_and_deleted(tmp_path: Path) -> None:
    profiles = JsonSpeakerProfileStore(tmp_path / "speakers.json")
    service = SpeakerRecognitionService(
        SequenceEngine([[1.0, 0.0], [0.99, 0.01]]),  # type: ignore[arg-type]
        profiles,
        StubRecorder(),  # type: ignore[arg-type]
        tmp_path / "audio",
        threshold=0.8,
    )

    enrolled = service.enroll_audio("Rajesh", b"RIFF transient sample")
    verified = service.verify_audio(b"RIFF another sample")

    assert enrolled.recognized is True
    assert verified.recognized is True
    assert list((tmp_path / "audio").iterdir()) == []
