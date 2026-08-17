"""Local speech-synthesis orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

from jarvis.capabilities.speech import SpeechSynthesizer


class SpeechSynthesisService:
    """Serialize speech rendering and remove temporary WAV files."""

    def __init__(self, synthesizer: SpeechSynthesizer, temporary_directory: Path) -> None:
        self._synthesizer = synthesizer
        self._temporary_directory = temporary_directory
        self._lock = asyncio.Lock()

    async def synthesize(self, text: str) -> bytes:
        """Return a locally rendered WAV payload."""
        self._temporary_directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=".wav", dir=self._temporary_directory, delete=False
        ) as temporary_file:
            destination = Path(temporary_file.name)
        async with self._lock:
            try:
                await asyncio.to_thread(self._synthesizer.synthesize_wav, text, destination)
                return await asyncio.to_thread(destination.read_bytes)
            finally:
                destination.unlink(missing_ok=True)
