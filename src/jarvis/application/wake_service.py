"""Wake-word session orchestration."""

from __future__ import annotations

import asyncio
import time

from jarvis.capabilities.speech import WakeWordDetector


class WakeWordService:
    """Serialize detector access and enforce a monotonic detection cooldown."""

    def __init__(self, detector: WakeWordDetector, cooldown_seconds: float) -> None:
        self._detector = detector
        self._cooldown_seconds = cooldown_seconds
        self._last_detection = float("-inf")
        self._lock = asyncio.Lock()

    async def reset(self) -> None:
        """Reset one listening session."""
        async with self._lock:
            await asyncio.to_thread(self._detector.reset)
            self._last_detection = float("-inf")

    async def process_pcm(self, pcm: bytes) -> tuple[bool, float]:
        """Process audio without blocking the API event loop."""
        async with self._lock:
            detected, score = await asyncio.to_thread(self._detector.process_pcm, pcm)
            now = time.monotonic()
            if detected and now - self._last_detection >= self._cooldown_seconds:
                self._last_detection = now
                return True, score
            return False, score
