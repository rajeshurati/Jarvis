"""Local speaker enrollment and recognition with transient recordings."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import uuid4

import numpy as np

from jarvis.capabilities.identity import (
    IdentityError,
    SpeakerEmbeddingEngine,
    SpeakerProfileStore,
    SpeakerResult,
)
from jarvis.capabilities.speech import AudioRecorder, SpeechError


class SpeakerRecognitionService:
    """Compare local speaker embeddings; never treat voice as sole authorization."""

    def __init__(
        self,
        engine: SpeakerEmbeddingEngine,
        profiles: SpeakerProfileStore,
        recorder: AudioRecorder,
        temporary_directory: Path,
        threshold: float = 0.65,
        sample_seconds: float = 5,
    ) -> None:
        self._engine = engine
        self._profiles = profiles
        self._recorder = recorder
        self._temporary_directory = temporary_directory
        self._threshold = threshold
        self._sample_seconds = sample_seconds
        self._lock = Lock()

    def profile_names(self) -> list[str]:
        return sorted(self._profiles.profiles())

    def _record_embedding(self) -> list[float]:
        self._temporary_directory.mkdir(parents=True, exist_ok=True)
        target = self._temporary_directory / f"speaker-{uuid4().hex}.wav"
        try:
            with self._lock:
                recorded = self._recorder.record_wav(target, self._sample_seconds)
                return self._engine.extract(recorded)
        except SpeechError as error:
            raise IdentityError("The microphone could not capture a speaker sample.") from error
        finally:
            target.unlink(missing_ok=True)

    def _uploaded_embedding(self, content: bytes) -> list[float]:
        if not content or len(content) > 25 * 1024 * 1024:
            raise IdentityError("A valid speaker WAV sample is required.")
        self._temporary_directory.mkdir(parents=True, exist_ok=True)
        target = self._temporary_directory / f"speaker-upload-{uuid4().hex}.wav"
        try:
            target.write_bytes(content)
            with self._lock:
                return self._engine.extract(target)
        except OSError as error:
            raise IdentityError("The speaker sample could not be processed.") from error
        finally:
            target.unlink(missing_ok=True)

    def enroll_audio(self, name: str, content: bytes) -> SpeakerResult:
        """Enroll from transient interactive-session audio, then discard the WAV."""
        normalized_name = name.strip()
        if not normalized_name:
            raise IdentityError("A speaker name is required.")
        self._profiles.add_sample(normalized_name, self._uploaded_embedding(content))
        return SpeakerResult("enrolled", True, normalized_name, 1.0)

    def verify_audio(self, content: bytes) -> SpeakerResult:
        """Recognize transient uploaded audio against derived local voiceprints."""
        if not self._profiles.profiles():
            return SpeakerResult("not_enrolled", False, None, None)
        return self._match_embedding(self._uploaded_embedding(content))

    def enroll_current(self, name: str) -> SpeakerResult:
        """Record, derive, persist, and immediately delete one voice sample."""
        normalized_name = name.strip()
        if not normalized_name:
            raise IdentityError("A speaker name is required.")
        self._profiles.add_sample(normalized_name, self._record_embedding())
        return SpeakerResult("enrolled", True, normalized_name, 1.0)

    def verify_current(self) -> SpeakerResult:
        """Recognize the current speaker against all enrolled local voiceprints."""
        if not self._profiles.profiles():
            return SpeakerResult("not_enrolled", False, None, None)
        return self._match_embedding(self._record_embedding())

    def _match_embedding(self, embedding: list[float]) -> SpeakerResult:
        profiles = self._profiles.profiles()
        if not profiles:
            return SpeakerResult("not_enrolled", False, None, None)
        candidate = np.asarray(embedding, dtype=np.float32)
        best_name: str | None = None
        best_similarity = -1.0
        for name, samples in profiles.items():
            for sample in samples:
                similarity = float(np.dot(candidate, np.asarray(sample, dtype=np.float32)))
                if similarity > best_similarity:
                    best_name, best_similarity = name, similarity
        recognized = best_name is not None and best_similarity >= self._threshold
        return SpeakerResult(
            "recognized" if recognized else "unrecognized",
            recognized,
            best_name if recognized else None,
            round(best_similarity, 4),
        )

    def delete_profile(self, name: str) -> bool:
        return self._profiles.delete(name)
