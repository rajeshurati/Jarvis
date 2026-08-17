"""Test configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config import Settings


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio, which is the production event loop."""
    return "asyncio"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Return isolated settings that cannot touch user data."""
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        artifact_dir=tmp_path / "artifacts",
        allow_network=False,
        speaker_model=tmp_path / "missing-speaker.onnx",
        yolo_model=tmp_path / "missing-yolo.pt",
    )
