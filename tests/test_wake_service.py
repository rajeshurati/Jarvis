"""Wake-word orchestration tests."""

from __future__ import annotations

import pytest

from jarvis.application.wake_service import WakeWordService


class FakeWakeDetector:
    """Detector controlled by the first PCM sample."""

    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def process_pcm(self, pcm: bytes) -> tuple[bool, float]:
        score = 0.9 if pcm == b"wake" else 0.1
        return score >= 0.5, score


@pytest.mark.anyio
async def test_wake_service_detects_and_resets() -> None:
    detector = FakeWakeDetector()
    service = WakeWordService(detector, cooldown_seconds=2)

    await service.reset()
    detected, score = await service.process_pcm(b"wake")

    assert detector.reset_count == 1
    assert detected is True
    assert score == 0.9


@pytest.mark.anyio
async def test_wake_service_suppresses_detection_during_cooldown() -> None:
    service = WakeWordService(FakeWakeDetector(), cooldown_seconds=60)

    first, _ = await service.process_pcm(b"wake")
    second, _ = await service.process_pcm(b"wake")

    assert first is True
    assert second is False
