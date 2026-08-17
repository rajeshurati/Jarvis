"""Local face authorization tests without real biometric data."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.adapters.identity.face_profiles import JsonFaceProfileStore
from jarvis.application.identity_service import FaceAuthorizationService
from jarvis.capabilities.identity import IdentityError


class Engine:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings

    def extract(self, image: bytes) -> list[list[float]]:
        assert image == b"jpeg"
        return self.embeddings


class Camera:
    def capture_jpeg(self) -> bytes:
        return b"jpeg"


def build_service(tmp_path: Path, embeddings: list[list[float]]) -> FaceAuthorizationService:
    return FaceAuthorizationService(
        Engine(embeddings), JsonFaceProfileStore(tmp_path / "faces.json"), Camera()
    )


def test_enrollment_authorizes_and_stores_only_embedding(tmp_path: Path) -> None:
    identity = build_service(tmp_path, [[1.0, 0.0]])

    result = identity.enroll_current("Rajesh")

    assert result.authorized and result.status == "enrolled"
    assert identity.profile_names() == ["Rajesh"]
    assert identity.is_session_authorized()
    assert "jpeg" not in (tmp_path / "faces.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("embeddings", [[], [[1.0, 0.0], [0.0, 1.0]]])
def test_enrollment_requires_exactly_one_face(
    tmp_path: Path, embeddings: list[list[float]]
) -> None:
    with pytest.raises(IdentityError, match="exactly one"):
        build_service(tmp_path, embeddings).enroll_current("Rajesh")


def test_verification_handles_not_enrolled_no_face_match_and_rejection(tmp_path: Path) -> None:
    identity = build_service(tmp_path, [[1.0, 0.0]])
    assert identity.verify_current().status == "not_enrolled"
    identity.enroll_current("Rajesh")

    identity._engine = Engine([])  # type: ignore[attr-defined]
    assert identity.verify_current().status == "no_face"
    identity._engine = Engine([[0.9, 0.1]])  # type: ignore[attr-defined]
    accepted = identity.verify_current()
    assert accepted.authorized and accepted.name == "Rajesh"
    identity._engine = Engine([[0.0, 1.0]])  # type: ignore[attr-defined]
    rejected = identity.verify_current()
    assert not rejected.authorized and rejected.status == "unauthorized"


def test_profile_deletion_revokes_session(tmp_path: Path) -> None:
    identity = build_service(tmp_path, [[1.0, 0.0]])
    identity.enroll_current("Rajesh")

    assert identity.delete_profile("rajesh")
    assert not identity.is_session_authorized()
    assert not identity.delete_profile("missing")


def test_profile_store_bounds_samples_and_rejects_invalid_data(tmp_path: Path) -> None:
    path = tmp_path / "faces.json"
    store = JsonFaceProfileStore(path, max_samples=2)
    for value in (0.1, 0.2, 0.3):
        store.add_sample("Rajesh", [value])
    assert store.profiles()["Rajesh"] == [[0.2], [0.3]]
    with pytest.raises(ValueError, match="required"):
        store.add_sample("", [])
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(IdentityError, match="invalid"):
        store.profiles()
