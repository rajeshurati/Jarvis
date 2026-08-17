"""Local text-to-speech service tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.application.speech_service import SpeechSynthesisService


class StubSynthesizer:
    def synthesize_wav(self, text: str, destination: Path) -> Path:
        destination.write_bytes(b"RIFF" + text.encode("utf-8"))
        return destination


@pytest.mark.anyio
async def test_speech_bytes_are_returned_and_temporary_file_removed(tmp_path: Path) -> None:
    directory = tmp_path / "speech"
    service = SpeechSynthesisService(StubSynthesizer(), directory)

    audio = await service.synthesize("hello")

    assert audio == b"RIFFhello"
    assert list(directory.iterdir()) == []
