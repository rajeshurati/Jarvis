"""Read-only runtime and local-model diagnostics."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis import __version__
from jarvis.core.config import Settings

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class ModelStatus(BaseModel):
    name: str
    size_bytes: int
    active: bool


class DiagnosticsResponse(BaseModel):
    version: str
    privacy: str
    free_disk_gb: float
    voice_ready: bool
    wake_word_ready: bool
    speech_ready: bool
    face_model_ready: bool
    speaker_model_ready: bool
    object_model_ready: bool
    configured_text_model: str
    configured_vision_model: str
    models: list[ModelStatus]


def _models(settings: Settings) -> list[ModelStatus]:
    """Read installed and currently loaded Ollama models from loopback only."""
    try:
        with urlopen(f"{settings.ollama_url}/api/tags", timeout=3) as response:
            installed = json.load(response).get("models", [])
        with urlopen(f"{settings.ollama_url}/api/ps", timeout=3) as response:
            active_names = {
                str(item.get("name")) for item in json.load(response).get("models", [])
            }
    except (OSError, URLError, json.JSONDecodeError):
        return []
    return [
        ModelStatus(
            name=str(item.get("name", "unknown")),
            size_bytes=int(item.get("size", 0)),
            active=str(item.get("name")) in active_names,
        )
        for item in installed
    ]


def _collect(settings: Settings) -> DiagnosticsResponse:
    try:
        settings.resolved_whisper_model()
        voice_ready = True
    except ValueError:
        voice_ready = False
    try:
        settings.resolved_wake_models()
        wake_ready = True
    except ValueError:
        wake_ready = False
    try:
        settings.resolved_piper_model()
        speech_ready = True
    except ValueError:
        speech_ready = False
    models = _models(settings)
    free_disk = shutil.disk_usage(Path.cwd().anchor).free / (1024**3)
    return DiagnosticsResponse(
        version=__version__,
        privacy=(
            "localhost-only; network disabled"
            if not settings.allow_network
            else "opt-in network"
        ),
        free_disk_gb=round(free_disk, 1),
        voice_ready=voice_ready,
        wake_word_ready=wake_ready,
        speech_ready=speech_ready,
        face_model_ready=settings.face_model_root.is_dir(),
        speaker_model_ready=settings.speaker_model.is_file(),
        object_model_ready=settings.yolo_model.is_file(),
        configured_text_model=settings.ollama_model,
        configured_vision_model=settings.ollama_vision_model,
        models=models,
    )


@router.get("", response_model=DiagnosticsResponse)
async def diagnostics(request: Request) -> DiagnosticsResponse:
    """Report readiness without opening the microphone, webcam, or screen."""
    return await asyncio.to_thread(_collect, request.app.state.settings)
