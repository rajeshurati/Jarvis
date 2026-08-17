"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from jarvis import __version__
from jarvis.adapters.identity.camera_snapshot_store import InMemoryCameraSnapshotStore
from jarvis.adapters.vision.snapshot_store import InMemoryScreenSnapshotStore
from jarvis.api.routes.assistant import router as assistant_router
from jarvis.api.routes.audit import router as audit_router
from jarvis.api.routes.camera import router as camera_router
from jarvis.api.routes.control import router as control_router
from jarvis.api.routes.diagnostics import router as diagnostics_router
from jarvis.api.routes.health import router as health_router
from jarvis.api.routes.identity import router as identity_router
from jarvis.api.routes.memory import router as memory_router
from jarvis.api.routes.presence import router as presence_router
from jarvis.api.routes.screen import router as screen_router
from jarvis.api.routes.speaker import router as speaker_router
from jarvis.api.routes.voice import router as voice_router
from jarvis.api.routes.wake import router as wake_router
from jarvis.api.routes.workflows import router as workflow_router
from jarvis.application.assistant_service import AssistantService
from jarvis.application.factory import (
    create_assistant_service,
    create_camera,
    create_identity_service,
    create_memory_store,
    create_presence_service,
    create_speaker_service,
    create_speech_service,
    create_voice_service,
    create_wake_service,
)
from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.application.speech_service import SpeechSynthesisService
from jarvis.application.voice_service import VoiceRecognitionService
from jarvis.application.wake_service import WakeWordService
from jarvis.capabilities.memory import MemoryStore
from jarvis.capabilities.speech import ModelUnavailableError
from jarvis.core.config import Settings, get_settings
from jarvis.core.logging import configure_logging, get_logger


def _is_benign_windows_transport_reset(context: dict[str, Any]) -> bool:
    """Identify the Proactor disconnect emitted when a local client closes normally."""
    error = context.get("exception")
    return isinstance(error, ConnectionResetError) and (
        getattr(error, "winerror", None) == 10054 or getattr(error, "errno", None) == 10054
    )


def create_app(
    settings: Settings | None = None,
    voice_service: VoiceRecognitionService | None = None,
    wake_service: WakeWordService | None = None,
    assistant_service: AssistantService | None = None,
    speech_service: SpeechSynthesisService | None = None,
    memory_store: MemoryStore | None = None,
    identity_service: FaceAuthorizationService | None = None,
) -> FastAPI:
    """Build an isolated app instance for production and tests."""
    app_settings = settings or get_settings()
    configure_logging(app_settings)
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        loop = asyncio.get_running_loop()
        previous_exception_handler = loop.get_exception_handler()

        def handle_loop_exception(
            event_loop: asyncio.AbstractEventLoop, context: dict[str, Any]
        ) -> None:
            if _is_benign_windows_transport_reset(context):
                logger.debug("localhost_client_disconnected")
            elif previous_exception_handler is not None:
                previous_exception_handler(event_loop, context)
            else:
                event_loop.default_exception_handler(context)

        loop.set_exception_handler(handle_loop_exception)
        app_settings.ensure_runtime_directories()
        removed_transient_files = app_settings.clear_stale_transient_media()
        logger.info(
            "application_started",
            extra={
                "environment": app_settings.environment,
                "removed_transient_files": removed_transient_files,
            },
        )
        presence = application.state.presence_service
        if app_settings.environment != "test":
            await presence.start()
        try:
            yield
        finally:
            if app_settings.environment != "test":
                await presence.stop()
            loop.set_exception_handler(previous_exception_handler)
            logger.info("application_stopped")

    app = FastAPI(
        title="Local Jarvis",
        version=__version__,
        description="Local-only assistant API with bounded speech recognition.",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.screen_snapshot_store = InMemoryScreenSnapshotStore()
    app.state.camera_snapshot_store = InMemoryCameraSnapshotStore()
    app.state.camera = create_camera(app_settings, app.state.camera_snapshot_store)
    if voice_service is not None:
        app.state.voice_service = voice_service
    else:
        try:
            app.state.voice_service = create_voice_service(app_settings)
        except ModelUnavailableError:
            logger.warning("voice_service_unavailable")
            app.state.voice_service = None
    if wake_service is not None:
        app.state.wake_service = wake_service
    else:
        try:
            app.state.wake_service = create_wake_service(app_settings)
        except ModelUnavailableError:
            logger.warning("wake_service_unavailable")
            app.state.wake_service = None
    app.state.memory_store = memory_store or create_memory_store(app_settings)
    app.state.identity_service = identity_service or create_identity_service(
        app_settings, app.state.camera
    )
    app.state.presence_service = create_presence_service(
        app_settings, app.state.identity_service, app.state.memory_store
    )
    app.state.speaker_service = create_speaker_service(app_settings)
    app.state.assistant_service = assistant_service or create_assistant_service(
        app_settings,
        app.state.memory_store,
        app.state.identity_service,
        app.state.presence_service,
        app.state.speaker_service,
        app.state.screen_snapshot_store,
        app.state.camera,
    )
    app.state.speech_service = speech_service or create_speech_service(app_settings)
    app.include_router(health_router)
    app.include_router(control_router)
    app.include_router(camera_router)
    app.include_router(diagnostics_router)
    app.include_router(screen_router)
    app.include_router(voice_router)
    app.include_router(wake_router)
    app.include_router(assistant_router)
    app.include_router(memory_router)
    app.include_router(identity_router)
    app.include_router(presence_router)
    app.include_router(speaker_router)
    app.include_router(audit_router)
    app.include_router(workflow_router)
    return app
