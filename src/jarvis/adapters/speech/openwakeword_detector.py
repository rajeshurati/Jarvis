"""openWakeWord ONNX adapter for the Hey Jarvis phrase."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from jarvis.capabilities.speech import ModelUnavailableError


class OpenWakeWordDetector:
    """Run streaming Hey Jarvis inference from local ONNX models."""

    _frame_samples = 1_280

    def __init__(
        self,
        wakeword_model: Path,
        melspectrogram_model: Path,
        embedding_model: Path,
        *,
        threshold: float = 0.5,
    ) -> None:
        self._wakeword_model = wakeword_model
        self._melspectrogram_model = melspectrogram_model
        self._embedding_model = embedding_model
        self._threshold = threshold
        self._model: Any | None = None
        self._samples = np.empty(0, dtype=np.int16)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from openwakeword.model import Model

            self._model = Model(
                wakeword_models=[str(self._wakeword_model)],
                inference_framework="onnx",
                melspec_model_path=str(self._melspectrogram_model),
                embedding_model_path=str(self._embedding_model),
                vad_threshold=0,
            )
        except Exception as error:
            raise ModelUnavailableError("Unable to load the local Hey Jarvis model") from error
        return self._model

    def reset(self) -> None:
        """Clear model features and buffered PCM."""
        self._samples = np.empty(0, dtype=np.int16)
        if self._model is not None:
            self._model.reset()

    def process_pcm(self, pcm: bytes) -> tuple[bool, float]:
        """Buffer arbitrary chunks and score complete 80 ms model frames."""
        if len(pcm) % 2:
            raise ValueError("PCM byte length must be even")
        incoming = np.frombuffer(pcm, dtype="<i2")
        self._samples = np.concatenate((self._samples, incoming))
        highest_score = 0.0
        model = self._load_model()
        while self._samples.size >= self._frame_samples:
            frame = self._samples[: self._frame_samples]
            self._samples = self._samples[self._frame_samples :]
            predictions = model.predict(frame)
            score = max(float(value) for value in predictions.values())
            highest_score = max(highest_score, score)
        return highest_score >= self._threshold, highest_score
