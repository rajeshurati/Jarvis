"""Speaker feature extraction and ONNX boundary tests."""

import wave
from pathlib import Path

import numpy as np
import pytest

from jarvis.adapters.identity.onnx_speaker_engine import ONNXSpeakerEmbeddingEngine
from jarvis.capabilities.identity import IdentityError


class FakeInput:
    name = "feats"


class FakeSession:
    def get_inputs(self) -> list[FakeInput]:
        return [FakeInput()]

    def run(self, outputs: object, inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
        assert inputs["feats"].shape[0] == 1
        assert inputs["feats"].shape[2] == 80
        return [np.asarray([[3.0, 4.0]], dtype=np.float32)]


def write_tone(path: Path, seconds: float = 1.2, sample_rate: int = 16_000) -> None:
    samples = np.arange(round(seconds * sample_rate))
    tone = (np.sin(2 * np.pi * 220 * samples / sample_rate) * 10_000).astype("<i2")
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(tone.tobytes())


def test_engine_produces_normalized_embedding(tmp_path: Path) -> None:
    model = tmp_path / "speaker.onnx"
    model.touch()
    sample = tmp_path / "voice.wav"
    write_tone(sample)
    engine = ONNXSpeakerEmbeddingEngine(model)
    engine._session = FakeSession()  # type: ignore[assignment]

    embedding = engine.extract(sample)

    assert embedding == pytest.approx([0.6, 0.8])


def test_engine_rejects_silence_and_short_audio(tmp_path: Path) -> None:
    model = tmp_path / "speaker.onnx"
    model.touch()
    silent = tmp_path / "silent.wav"
    short = tmp_path / "short.wav"
    with wave.open(str(silent), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(np.zeros(16_000, dtype="<i2").tobytes())
    write_tone(short, seconds=0.5)
    engine = ONNXSpeakerEmbeddingEngine(model)

    with pytest.raises(IdentityError, match="silent"):
        engine.extract(silent)
    with pytest.raises(IdentityError, match="between 1 and 20"):
        engine.extract(short)
