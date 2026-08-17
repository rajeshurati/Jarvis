"""Face authorization API tests with synthetic embeddings."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.adapters.identity.face_profiles import JsonFaceProfileStore
from jarvis.api.app import create_app
from jarvis.application.assistant_service import AssistantService
from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.capabilities.automation import ActionResult
from jarvis.capabilities.language import LanguageMessage
from jarvis.core.config import Settings


class Engine:
    def extract(self, image: bytes) -> list[list[float]]:
        return [] if image == b"none" else [[1.0, 0.0]]


class Camera:
    def capture_jpeg(self) -> bytes:
        return b"face"


class Model:
    def complete(self, messages: list[LanguageMessage]) -> str:
        return "ok"


class Automation:
    def try_execute(self, command: str) -> ActionResult | None:
        return None


def build_app(test_settings: Settings, tmp_path: Path):  # type: ignore[no-untyped-def]
    identity = FaceAuthorizationService(
        Engine(), JsonFaceProfileStore(tmp_path / "faces.json"), Camera()
    )
    return create_app(
        test_settings,
        assistant_service=AssistantService(Model(), Automation()),
        identity_service=identity,
    )


def test_identity_enrollment_verification_status_and_deletion(
    test_settings: Settings, tmp_path: Path
) -> None:
    with TestClient(build_app(test_settings, tmp_path)) as client:
        assert client.get("/identity/status").json()["enrolled_profiles"] == []
        enrolled = client.post(
            "/identity/enroll",
            data={"name": "Rajesh"},
            files={"image": ("face.jpg", b"face")},
        )
        assert enrolled.status_code == 200 and enrolled.json()["authorized"]
        assert client.post("/identity/verify-current").json()["authorized"]
        assert client.post("/identity/verify", files={"image": ("face.jpg", b"face")}).json()[
            "authorized"
        ]
        assert client.delete("/identity/profiles/Rajesh").status_code == 204
        assert client.delete("/identity/profiles/Rajesh").status_code == 404


def test_identity_api_reports_detection_error(test_settings: Settings, tmp_path: Path) -> None:
    with TestClient(build_app(test_settings, tmp_path)) as client:
        response = client.post(
            "/identity/enroll",
            data={"name": "Rajesh"},
            files={"image": ("none.jpg", b"none")},
        )
    assert response.status_code == 422
