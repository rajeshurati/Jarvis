"""Local ONNX speaker embeddings from log-Mel filter-bank features."""

from __future__ import annotations

import wave
from pathlib import Path
from threading import Lock
from typing import Any, cast

import numpy as np

from jarvis.capabilities.identity import IdentityError


class ONNXSpeakerEmbeddingEngine:
    """Run a WeSpeaker-compatible ONNX model entirely on CPU."""

    _sample_rate = 16_000
    _mel_bins = 80

    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise ValueError(f"Local speaker model is missing: {model_path}")
        self._model_path = model_path
        self._session: Any | None = None
        self._lock = Lock()

    def _model(self) -> Any:
        if self._session is not None:
            return self._session
        with self._lock:
            if self._session is None:
                try:
                    import onnxruntime as ort  # type: ignore[import-untyped]

                    self._session = ort.InferenceSession(
                        str(self._model_path.resolve()), providers=["CPUExecutionProvider"]
                    )
                except Exception as error:
                    raise IdentityError("The local speaker model could not be loaded.") from error
        return self._session

    @staticmethod
    def _read_wav(path: Path) -> tuple[np.ndarray, int]:
        try:
            with wave.open(str(path.resolve(strict=True)), "rb") as audio:
                channels = audio.getnchannels()
                sample_width = audio.getsampwidth()
                sample_rate = audio.getframerate()
                frames = audio.getnframes()
                payload = audio.readframes(frames)
        except (OSError, EOFError, wave.Error) as error:
            raise IdentityError("The speaker sample is not a readable WAV file.") from error
        if sample_width != 2 or channels < 1 or not 8_000 <= sample_rate <= 48_000:
            raise IdentityError("Speaker samples require 16-bit PCM WAV audio.")
        samples = np.frombuffer(payload, dtype="<i2").astype(np.float32)
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        return samples / 32768.0, sample_rate

    @classmethod
    def _resample(cls, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        if sample_rate == cls._sample_rate:
            return samples
        output_length = round(len(samples) * cls._sample_rate / sample_rate)
        source = np.arange(len(samples), dtype=np.float64)
        target = np.linspace(0, max(len(samples) - 1, 0), output_length)
        return cast(
            np.ndarray[Any, np.dtype[np.float32]],
            np.interp(target, source, samples).astype(np.float32),
        )

    @staticmethod
    def _hz_to_mel(value: float) -> float:
        return cast(float, 2595.0 * np.log10(1.0 + value / 700.0))

    @staticmethod
    def _mel_to_hz(value: np.ndarray) -> np.ndarray:
        return 700.0 * (np.power(10.0, value / 2595.0) - 1.0)

    @classmethod
    def _features(cls, samples: np.ndarray) -> np.ndarray:
        if len(samples) < cls._sample_rate or len(samples) > cls._sample_rate * 20:
            raise IdentityError("Speak clearly for between 1 and 20 seconds.")
        if float(np.sqrt(np.mean(np.square(samples)))) < 0.003:
            raise IdentityError("The speaker sample is silent or too quiet.")
        emphasized = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
        frames = np.lib.stride_tricks.sliding_window_view(emphasized, 400)[::160]
        power = np.abs(np.fft.rfft(frames * np.hamming(400), n=512)) ** 2 / 512
        mel_points = np.linspace(cls._hz_to_mel(20), cls._hz_to_mel(7_600), cls._mel_bins + 2)
        bins = np.floor((513 * cls._mel_to_hz(mel_points)) / cls._sample_rate).astype(int)
        filters = np.zeros((cls._mel_bins, 257), dtype=np.float32)
        for index in range(cls._mel_bins):
            left, center, right = bins[index : index + 3]
            if center > left:
                filters[index, left:center] = np.arange(center - left) / (center - left)
            if right > center:
                filters[index, center:right] = np.arange(right - center, 0, -1) / (
                    right - center
                )
        features = np.log(np.maximum(power @ filters.T, 1e-10)).astype(np.float32)
        features -= features.mean(axis=0, keepdims=True)
        return features[None, :, :]

    def extract(self, audio_path: Path) -> list[float]:
        """Validate audio, compute features, and return a normalized embedding."""
        samples, sample_rate = self._read_wav(audio_path)
        features = self._features(self._resample(samples, sample_rate))
        try:
            model = self._model()
            input_name = model.get_inputs()[0].name
            output = np.asarray(model.run(None, {input_name: features})[0], dtype=np.float32)
        except IdentityError:
            raise
        except Exception as error:
            raise IdentityError("Local speaker analysis failed.") from error
        embedding = output.reshape(-1)
        norm = float(np.linalg.norm(embedding))
        if not np.isfinite(norm) or norm <= 0:
            raise IdentityError("The speaker model returned an invalid voiceprint.")
        return cast(list[float], (embedding / norm).tolist())
