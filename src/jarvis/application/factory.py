"""Composition root for application services."""

from __future__ import annotations

from pathlib import Path

from jarvis.adapters.audio.sounddevice_recorder import SoundDeviceRecorder
from jarvis.adapters.automation.developer_commands import SafeDeveloperCommandService
from jarvis.adapters.automation.pyautogui_input import PyAutoGUIDesktopInput
from jarvis.adapters.automation.windows_desktop import WindowsDesktopAutomation
from jarvis.adapters.automation.windows_system import WindowsSystemController
from jarvis.adapters.files.document_reader import LocalDocumentReader
from jarvis.adapters.files.local_manager import LocalFileManager
from jarvis.adapters.files.local_search import LocalFileSearch
from jarvis.adapters.identity.camera_snapshot_store import (
    FallbackCamera,
    InMemoryCameraSnapshotStore,
)
from jarvis.adapters.identity.face_profiles import JsonFaceProfileStore
from jarvis.adapters.identity.insightface_engine import InsightFaceEmbeddingEngine
from jarvis.adapters.identity.onnx_speaker_engine import ONNXSpeakerEmbeddingEngine
from jarvis.adapters.identity.opencv_camera import OpenCVCamera
from jarvis.adapters.identity.voice_profiles import JsonSpeakerProfileStore
from jarvis.adapters.language.ollama_client import OllamaLanguageModel
from jarvis.adapters.language.ollama_vision import OllamaVisionModel
from jarvis.adapters.memory.sqlite_store import SQLiteMemoryStore
from jarvis.adapters.productivity.gmail_oauth import GmailOAuthGateway
from jarvis.adapters.productivity.tls_email import TLSMailGateway
from jarvis.adapters.productivity.web_research import WebResearchService
from jarvis.adapters.speech.faster_whisper import FasterWhisperTranscriber
from jarvis.adapters.speech.openwakeword_detector import OpenWakeWordDetector
from jarvis.adapters.speech.piper_synthesizer import PiperSynthesizer
from jarvis.adapters.vision.isolated_yolo_detector import IsolatedYOLOObjectDetector
from jarvis.adapters.vision.mss_capture import MssScreenCapturer
from jarvis.adapters.vision.rapidocr_reader import RapidOCRReader
from jarvis.adapters.vision.snapshot_store import (
    FallbackScreenCapturer,
    InMemoryScreenSnapshotStore,
)
from jarvis.application.assistant_service import AssistantService
from jarvis.application.code_service import LocalCodeService
from jarvis.application.document_service import LocalDocumentService
from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.application.object_service import ObjectRecognitionService
from jarvis.application.planner_service import LocalPlannerService
from jarvis.application.presence_service import PresenceMonitorService
from jarvis.application.productivity_service import LocalProductivityService
from jarvis.application.screen_service import ScreenUnderstandingService
from jarvis.application.semantic_desktop_service import SemanticDesktopService
from jarvis.application.speaker_router import SpeakerCommandRouter
from jarvis.application.speaker_service import SpeakerRecognitionService
from jarvis.application.speech_service import SpeechSynthesisService
from jarvis.application.tool_router import JarvisToolRouter
from jarvis.application.voice_service import VoiceRecognitionService
from jarvis.application.wake_service import WakeWordService
from jarvis.application.workflow_service import WorkflowService
from jarvis.capabilities.identity import Camera
from jarvis.capabilities.memory import MemoryStore
from jarvis.capabilities.productivity import EmailGateway
from jarvis.capabilities.speech import ModelUnavailableError
from jarvis.core.config import Settings


def create_voice_service(settings: Settings) -> VoiceRecognitionService:
    """Wire local Phase 2 adapters to the voice use case."""
    try:
        model_reference = settings.resolved_whisper_model()
    except ValueError as error:
        raise ModelUnavailableError(str(error)) from error
    transcriber = FasterWhisperTranscriber(
        model_reference,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language=settings.whisper_language,
    )
    transcriber.warm_up()
    return VoiceRecognitionService(
        recorder=SoundDeviceRecorder(
            sample_rate=settings.audio_sample_rate,
            channels=settings.audio_channels,
            device=settings.audio_device_name or settings.audio_device_index,
            channel_index=settings.audio_channel_index,
        ),
        transcriber=transcriber,
        max_recording_seconds=settings.max_recording_seconds,
        temporary_directory=settings.data_dir / "temporary_audio",
    )


def create_wake_service(settings: Settings) -> WakeWordService:
    """Wire the local ONNX wake detector to its streaming use case."""
    try:
        models = settings.resolved_wake_models()
    except ValueError as error:
        raise ModelUnavailableError(str(error)) from error
    detector = OpenWakeWordDetector(
        wakeword_model=models["wakeword"],
        melspectrogram_model=models["melspectrogram"],
        embedding_model=models["embedding"],
        threshold=settings.wake_threshold,
    )
    return WakeWordService(detector, settings.wake_cooldown_seconds)


def create_memory_store(settings: Settings) -> SQLiteMemoryStore:
    """Create and migrate the authoritative local database."""
    store = SQLiteMemoryStore(settings.data_dir / "jarvis.db")
    store.initialize()
    return store


def create_camera(
    settings: Settings, snapshot: InMemoryCameraSnapshotStore
) -> FallbackCamera:
    """Create a webcam source that survives Windows background-session isolation."""
    return FallbackCamera(OpenCVCamera(settings.face_camera_index), snapshot)


def create_identity_service(
    settings: Settings, camera: Camera | None = None
) -> FaceAuthorizationService:
    """Wire local camera capture, InsightFace, and derived profile storage."""
    return FaceAuthorizationService(
        InsightFaceEmbeddingEngine(
            str(settings.face_model_root.resolve()), settings.face_model_name
        ),
        JsonFaceProfileStore(settings.data_dir / "authorized_faces.json"),
        camera or OpenCVCamera(settings.face_camera_index),
        settings.face_similarity_threshold,
        settings.face_session_minutes,
    )


def create_presence_service(
    settings: Settings, identity: FaceAuthorizationService, memory: MemoryStore
) -> PresenceMonitorService:
    """Wire transient webcam sampling to transition-only local persistence."""
    return PresenceMonitorService(
        identity,
        memory,
        settings.presence_interval_seconds,
        settings.presence_monitor_enabled,
    )


def create_speaker_service(settings: Settings) -> SpeakerRecognitionService | None:
    """Create local speaker recognition only when explicit ONNX weights exist."""
    if not settings.speaker_model.is_file():
        return None
    return SpeakerRecognitionService(
        ONNXSpeakerEmbeddingEngine(settings.speaker_model),
        JsonSpeakerProfileStore(settings.data_dir / "authorized_speakers.json"),
        SoundDeviceRecorder(
            sample_rate=settings.audio_sample_rate,
            channels=settings.audio_channels,
            device=settings.audio_device_name or settings.audio_device_index,
            channel_index=settings.audio_channel_index,
        ),
        settings.data_dir / "temporary_speaker_audio",
        settings.speaker_similarity_threshold,
        settings.speaker_sample_seconds,
    )


def create_assistant_service(
    settings: Settings,
    memory: MemoryStore | None = None,
    identity: FaceAuthorizationService | None = None,
    presence: PresenceMonitorService | None = None,
    speaker: SpeakerRecognitionService | None = None,
    screen_snapshot: InMemoryScreenSnapshotStore | None = None,
    camera: Camera | None = None,
) -> AssistantService:
    """Wire local language inference to controlled Windows capabilities."""
    memory_store = memory or create_memory_store(settings)
    home = Path.home()
    user_roots = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
    }
    file_search = LocalFileSearch(list(user_roots.values()))
    direct_screen_capturer = MssScreenCapturer()
    screen_capturer = (
        FallbackScreenCapturer(direct_screen_capturer, screen_snapshot)
        if screen_snapshot is not None
        else direct_screen_capturer
    )
    screen = ScreenUnderstandingService(
        screen_capturer,
        OllamaVisionModel(
            settings.ollama_url,
            settings.ollama_vision_model,
            settings.ollama_timeout_seconds,
        ),
    )
    language_model = OllamaLanguageModel(
        settings.ollama_url,
        settings.ollama_model,
        settings.ollama_timeout_seconds,
    )
    long_form_model = OllamaLanguageModel(
        settings.ollama_url,
        settings.ollama_model,
        settings.ollama_timeout_seconds,
        maximum_tokens=768,
        context_window=4_096,
    )
    ocr = RapidOCRReader()
    documents = LocalDocumentService(
        file_search,
        LocalDocumentReader(),
        ocr,
        long_form_model,
    )
    workflows = WorkflowService(memory_store)
    planner = LocalPlannerService(language_model, workflows)
    research = WebResearchService(
        long_form_model,
        settings.artifact_dir,
        settings.allow_network,
    )
    desktop_input = PyAutoGUIDesktopInput()
    semantic_desktop = SemanticDesktopService(screen_capturer, ocr, desktop_input)
    productivity = LocalProductivityService(settings.artifact_dir, long_form_model)
    email_gateway: EmailGateway | None = None
    if settings.gmail_oauth_is_configured():
        email_gateway = GmailOAuthGateway(settings.gmail_oauth_token_file)
    elif settings.email_is_configured():
        if settings.email_password is None:  # pragma: no cover - guaranteed by predicate
            raise ValueError("Configured email password is unavailable.")
        email_gateway = TLSMailGateway(
            settings.email_address or "",
            settings.email_username or "",
            settings.email_password.get_secret_value(),
            settings.smtp_host or "",
            settings.smtp_port,
            settings.imap_host or "",
            settings.imap_port,
            settings.email_timeout_seconds,
        )
    objects = None
    if settings.yolo_model.is_file():
        objects = ObjectRecognitionService(
            camera or OpenCVCamera(settings.face_camera_index),
            IsolatedYOLOObjectDetector(settings.yolo_model, settings.yolo_confidence),
        )
    base_tools = JarvisToolRouter(
        WindowsDesktopAutomation(),
        memory_store,
        screen,
        file_search,
        identity,
        documents,
        desktop_input,
        LocalFileManager(user_roots),
        workflows,
        semantic_desktop,
        productivity,
        email_gateway,
        objects,
        presence,
        None,
        planner,
        research,
        WindowsSystemController(),
        LocalCodeService(long_form_model, settings.data_dir / "code"),
        SafeDeveloperCommandService(Path.cwd()),
        settings.email_address,
    )
    tools = SpeakerCommandRouter(base_tools, speaker)
    workflows.bind_executor(tools)
    return AssistantService(
        language_model,
        tools,
        settings.assistant_history_messages,
        memory_store,
    )


def create_speech_service(settings: Settings) -> SpeechSynthesisService:
    """Wire the installed local Piper voice to temporary WAV rendering."""
    return SpeechSynthesisService(
        PiperSynthesizer(settings.resolved_piper_model()),
        settings.data_dir / "temporary_speech",
    )
