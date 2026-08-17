"""Configuration tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.core.config import Settings


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(host="0.0.0.0")


def test_privacy_defaults_are_restrictive() -> None:
    settings = Settings(_env_file=None)

    assert settings.allow_network is False
    assert settings.require_confirmation is True
    assert settings.host == "127.0.0.1"
    assert settings.allow_model_download is False
    assert settings.email_is_configured() is False


def test_email_requires_network_and_complete_tls_configuration() -> None:
    partial = Settings(allow_network=True, email_address="person@example.com")
    complete = Settings(
        allow_network=True,
        email_address="person@example.com",
        email_username="person@example.com",
        email_password="secret",
        smtp_host="smtp.example.com",
        imap_host="imap.example.com",
    )

    assert partial.email_is_configured() is False
    assert complete.email_is_configured() is True


def test_missing_model_is_rejected_by_default(tmp_path) -> None:
    settings = Settings(whisper_model=str(tmp_path / "missing"))

    with pytest.raises(ValueError, match="not available locally"):
        settings.resolved_whisper_model()


def test_existing_local_model_is_resolved(tmp_path) -> None:
    model_directory = tmp_path / "model"
    model_directory.mkdir()
    for filename in ("config.json", "model.bin", "tokenizer.json"):
        (model_directory / filename).touch()

    resolved = Settings(whisper_model=str(model_directory)).resolved_whisper_model()

    assert resolved == str(model_directory.resolve())


def test_incomplete_local_model_is_rejected(tmp_path) -> None:
    model_directory = tmp_path / "model"
    model_directory.mkdir()
    (model_directory / "model.bin").touch()

    with pytest.raises(ValueError, match="complete Whisper model"):
        Settings(whisper_model=str(model_directory)).resolved_whisper_model()


def test_complete_wake_models_are_resolved(tmp_path) -> None:
    for filename in (
        "hey_jarvis_v0.1.onnx",
        "melspectrogram.onnx",
        "embedding_model.onnx",
    ):
        (tmp_path / filename).touch()

    models = Settings(wake_model_dir=tmp_path).resolved_wake_models()

    assert models["wakeword"].name == "hey_jarvis_v0.1.onnx"


def test_missing_wake_models_are_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="Wake-word model files are missing"):
        Settings(wake_model_dir=tmp_path).resolved_wake_models()


def test_stale_transient_media_is_removed_without_touching_other_data(tmp_path) -> None:
    data = tmp_path / "data"
    settings = Settings(data_dir=data, artifact_dir=data / "artifacts")
    settings.ensure_runtime_directories()
    transient = data / "temporary_audio" / "old.wav"
    transient.parent.mkdir()
    transient.write_bytes(b"private audio")
    persistent = data / "keep.txt"
    persistent.write_text("keep", encoding="utf-8")

    removed = settings.clear_stale_transient_media()

    assert removed == 1
    assert not transient.exists()
    assert persistent.read_text(encoding="utf-8") == "keep"
