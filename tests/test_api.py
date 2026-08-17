"""API contract tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.api.app import _is_benign_windows_transport_reset, create_app
from jarvis.application.assistant_service import AssistantService
from jarvis.application.speech_service import SpeechSynthesisService
from jarvis.application.voice_service import VoiceRecognitionService
from jarvis.application.wake_service import WakeWordService
from jarvis.capabilities.automation import ActionResult
from jarvis.capabilities.language import LanguageMessage
from jarvis.capabilities.speech import AudioDevice, Transcript
from jarvis.core.config import Settings


class FakeRecorder:
    def list_input_devices(self) -> list[AudioDevice]:
        return [AudioDevice(1, "Test microphone", 1, 16_000)]

    def record_wav(self, destination: Path, duration_seconds: float) -> Path:
        destination.write_bytes(b"test audio")
        return destination


class FakeTranscriber:
    def transcribe(self, audio_path: Path) -> Transcript:
        return Transcript("Hello Jarvis", "en", 0.99, 1.25)


class FakeWakeDetector:
    def reset(self) -> None:
        pass

    def process_pcm(self, pcm: bytes) -> tuple[bool, float]:
        return (True, 0.9) if pcm == b"wake" else (False, 0.1)


class FakeLanguageModel:
    def complete(self, messages: list[LanguageMessage]) -> str:
        return f"Local answer to {messages[-1].content}"


class FakeAutomation:
    def try_execute(self, command: str) -> ActionResult | None:
        return None


class FakeSynthesizer:
    def synthesize_wav(self, text: str, destination: Path) -> Path:
        destination.write_bytes(b"RIFF" + b"\0" * 64)
        return destination


def test_health_is_local_and_healthy(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.18.0",
        "environment": "test",
        "local_only": True,
    }


def test_native_voice_runtime_status_is_publishable(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        initial = client.get("/voice/runtime-status")
        updated = client.put(
            "/voice/runtime-status",
            json={
                "running": True,
                "enabled": True,
                "state": "listening",
                "last_error": None,
            },
        )
        current = client.get("/voice/runtime-status")

    assert initial.json()["state"] == "unavailable"
    assert updated.status_code == 200
    assert current.json()["running"] is True
    assert current.json()["state"] == "listening"
    assert current.json()["updated_at"]


def test_native_voice_runtime_status_fails_closed_when_stale(
    test_settings: Settings,
) -> None:
    from datetime import UTC, datetime, timedelta

    from jarvis.api.routes.voice import NativeRuntimeStatus

    app = create_app(test_settings)
    with TestClient(app) as client:
        app.state.native_voice_status = NativeRuntimeStatus(
            running=True,
            enabled=True,
            state="listening",
            updated_at=datetime.now(UTC) - timedelta(seconds=30),
        )
        response = client.get("/voice/runtime-status")

    assert response.json()["running"] is False
    assert response.json()["state"] == "stale"


def test_control_center_exposes_nontechnical_local_management(
    test_settings: Settings,
) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/control")

    assert response.status_code == 200
    assert "Jarvis Control Center" in response.text
    assert "Memory" in response.text
    assert "Projects" in response.text
    assert "Reminders" in response.text
    assert "Room monitoring" in response.text
    assert "camera stays fully off" in response.text
    assert "https://" not in response.text


def test_only_windows_connection_reset_is_treated_as_benign() -> None:
    reset = ConnectionResetError(10054, "local client closed")

    assert _is_benign_windows_transport_reset({"exception": reset}) is True
    assert _is_benign_windows_transport_reset({"exception": RuntimeError("failure")}) is False
    assert _is_benign_windows_transport_reset({}) is False


def test_presence_controls_are_local_and_persistent(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        status = client.get("/presence/status")
        disabled = client.post("/presence/disable")
        events = client.get("/presence/events")
        enabled = client.post("/presence/enable")

    assert status.status_code == 200
    assert disabled.json()["enabled"] is False
    assert events.json() == []
    assert enabled.json()["enabled"] is True


def test_speaker_status_truthfully_reports_missing_model(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        status = client.get("/speaker/status")
        enrollment = client.post("/speaker/enroll-current")

    assert status.status_code == 200
    assert status.json()["available"] is False
    assert enrollment.status_code == 503


def test_lifespan_creates_runtime_directories(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)):
        pass

    assert test_settings.data_dir.is_dir()
    assert test_settings.log_dir.is_dir()


def test_diagnostics_are_read_only_and_report_configuration(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured_text_model"] == "qwen3:1.7b"
    assert payload["privacy"] == "localhost-only; network disabled"


def test_memory_search_endpoint(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        client.put(
            "/memory",
            json={"category": "preference", "key": "editor", "value": "VS Code"},
        )
        response = client.get("/memory/search", params={"query": "code"})

    assert response.status_code == 200
    assert response.json()[0]["key"] == "editor"


def test_project_planning_endpoints(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        project = client.post(
            "/projects", json={"name": "Jarvis", "objective": "Ship local AI"}
        ).json()
        task = client.post(
            f"/projects/{project['id']}/tasks", json={"title": "Run acceptance tests"}
        ).json()
        updated = client.patch(
            f"/project-tasks/{task['id']}", json={"status": "completed"}
        )
        note = client.post(
            f"/projects/{project['id']}/notes",
            json={"kind": "risk", "content": "Low disk space"},
        )
        notes = client.get(f"/projects/{project['id']}/notes")

    assert updated.json()["status"] == "completed"
    assert note.status_code == 201
    assert notes.json()[0]["content"] == "Low disk space"


def test_interactive_screen_snapshot_is_memory_only(test_settings: Settings) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"transient"
    with TestClient(create_app(test_settings)) as client:
        update = client.put(
            "/screen/snapshot",
            content=png,
            headers={"Content-Type": "image/png", "X-Screen-Left": "-20"},
        )
        snapshot_status = client.get("/screen/snapshot/status")

    assert update.status_code == 204
    assert snapshot_status.json()["available"] is True


def test_interactive_camera_snapshot_is_memory_only(test_settings: Settings) -> None:
    jpeg = b"\xff\xd8\xff" + b"transient"
    with TestClient(create_app(test_settings)) as client:
        update = client.put(
            "/camera/snapshot", content=jpeg, headers={"Content-Type": "image/jpeg"}
        )
        snapshot_status = client.get("/camera/snapshot/status")

    assert update.status_code == 204
    assert snapshot_status.json()["available"] is True


def test_voice_recording_endpoint(test_settings: Settings) -> None:
    service = VoiceRecognitionService(
        FakeRecorder(),
        FakeTranscriber(),
        max_recording_seconds=10,
        temporary_directory=test_settings.data_dir,
    )
    with TestClient(create_app(test_settings, voice_service=service)) as client:
        response = client.post("/voice/transcribe-recording?duration_seconds=2")

    assert response.status_code == 200
    assert response.json()["text"] == "Hello Jarvis"


def test_voice_devices_endpoint(test_settings: Settings) -> None:
    service = VoiceRecognitionService(
        FakeRecorder(),
        FakeTranscriber(),
        max_recording_seconds=10,
        temporary_directory=test_settings.data_dir,
    )
    with TestClient(create_app(test_settings, voice_service=service)) as client:
        response = client.get("/voice/devices")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Test microphone"


def test_voice_browser_page(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/voice/transcribe-recording")

    assert response.status_code == 200
    assert "Record and transcribe" in response.text
    assert "getUserMedia" in response.text


def test_browser_audio_upload_endpoint(test_settings: Settings) -> None:
    service = VoiceRecognitionService(
        FakeRecorder(),
        FakeTranscriber(),
        max_recording_seconds=10,
        temporary_directory=test_settings.data_dir,
    )
    with TestClient(create_app(test_settings, voice_service=service)) as client:
        response = client.post(
            "/voice/transcribe-upload",
            files={"audio": ("recording.webm", b"test audio", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "Hello Jarvis"


def test_wake_control_page(test_settings: Settings) -> None:
    wake_service = WakeWordService(FakeWakeDetector(), cooldown_seconds=0)
    with TestClient(create_app(test_settings, wake_service=wake_service)) as client:
        response = client.get("/wake")

    assert response.status_code == 200
    assert "Hey Jarvis" in response.text
    assert "WebSocket" in response.text
    assert "Background listening active" in response.text


def test_wake_websocket_detects_phrase(test_settings: Settings) -> None:
    wake_service = WakeWordService(FakeWakeDetector(), cooldown_seconds=0)
    with (
        TestClient(create_app(test_settings, wake_service=wake_service)) as client,
        client.websocket_connect("/wake/ws") as websocket,
    ):
        websocket.send_bytes(b"wake")
        message = websocket.receive_json()

    assert message["type"] == "detected"
    assert message["score"] == 0.9


def test_assistant_response_endpoint(test_settings: Settings) -> None:
    assistant = AssistantService(FakeLanguageModel(), FakeAutomation())
    with TestClient(create_app(test_settings, assistant_service=assistant)) as client:
        response = client.post("/assistant/respond", json={"text": "hello"})

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Local answer to hello",
        "action": None,
        "target_url": None,
        "desktop_action": None,
    }


def test_local_speech_endpoint(test_settings: Settings) -> None:
    speech = SpeechSynthesisService(FakeSynthesizer(), test_settings.data_dir / "speech")
    with TestClient(create_app(test_settings, speech_service=speech)) as client:
        response = client.post("/assistant/speak", json={"text": "Good morning"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
