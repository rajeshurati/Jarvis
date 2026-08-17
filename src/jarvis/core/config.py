"""Validated application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings with privacy-preserving defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JARVIS_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path = Path("data")
    log_dir: Path = Path("logs")
    artifact_dir: Path = Path("data/artifacts")
    require_confirmation: bool = True
    allow_network: bool = False
    audio_sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    audio_channels: int = Field(default=1, ge=1, le=8)
    audio_device_index: int | None = Field(default=None, ge=0)
    audio_device_name: str | None = None
    audio_channel_index: int = Field(default=0, ge=0, le=7)
    max_recording_seconds: float = Field(default=30.0, gt=0, le=120)
    whisper_model: str = "models/whisper"
    whisper_device: Literal["auto", "cpu", "cuda"] = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = "en"
    allow_model_download: bool = False
    wake_model_dir: Path = Path("models/wakeword")
    wake_threshold: float = Field(default=0.2, gt=0, lt=1)
    wake_cooldown_seconds: float = Field(default=2.0, ge=0, le=30)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    ollama_vision_model: str = "qwen3.5:0.8b"
    ollama_timeout_seconds: float = Field(default=90, ge=5, le=300)
    assistant_history_messages: int = Field(default=12, ge=2, le=50)
    piper_model: Path = Path("models/piper/en_US-lessac-medium.onnx")
    face_model_root: Path = Path("models/insightface")
    face_model_name: str = "buffalo_l"
    face_similarity_threshold: float = Field(default=0.45, ge=0.2, le=0.9)
    face_camera_index: int = Field(default=0, ge=0, le=10)
    face_session_minutes: int = Field(default=5, ge=1, le=60)
    yolo_model: Path = Path("models/yolo/yolo11n.pt")
    yolo_confidence: float = Field(default=0.35, ge=0.1, le=0.95)
    presence_monitor_enabled: bool = False
    presence_interval_seconds: float = Field(default=10, ge=2, le=300)
    speaker_model: Path = Path("models/speaker/wespeaker.onnx")
    speaker_similarity_threshold: float = Field(default=0.65, ge=0.3, le=0.95)
    speaker_sample_seconds: float = Field(default=5, ge=2, le=15)
    email_address: str | None = None
    email_username: str | None = None
    email_password: SecretStr | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=465, ge=1, le=65535)
    imap_host: str | None = None
    imap_port: int = Field(default=993, ge=1, le=65535)
    email_timeout_seconds: float = Field(default=20, ge=5, le=60)
    gmail_oauth_client_file: Path = Path("data/google-oauth-client.json")
    gmail_oauth_token_file: Path = Path("data/google-oauth-token.json")

    def gmail_oauth_is_configured(self) -> bool:
        """Return true only when explicit network access and an OAuth token exist."""
        return self.allow_network and self.gmail_oauth_token_file.is_file()

    def email_is_configured(self) -> bool:
        """Return true only when network use and every mail credential are explicit."""
        return self.allow_network and all(
            (
                self.email_address,
                self.email_username,
                self.email_password,
                self.smtp_host,
                self.imap_host,
            )
        )

    @field_validator("host")
    @classmethod
    def host_must_be_local(cls, value: str) -> str:
        """Prevent accidental network exposure in the initial release."""
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Phase 1 only permits a loopback host")
        return value

    @field_validator("ollama_url")
    @classmethod
    def ollama_must_be_local(cls, value: str) -> str:
        """Prevent prompts from being sent to a remote model endpoint."""
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama must use a localhost HTTP endpoint")
        return value.rstrip("/")

    def ensure_runtime_directories(self) -> None:
        """Create private runtime directories when the app starts."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def clear_stale_transient_media(self) -> int:
        """Remove crash-left audio files from fixed private temporary directories."""
        removed = 0
        for name in ("temporary_audio", "temporary_speech", "temporary_speaker_audio"):
            directory = self.data_dir / name
            directory.mkdir(parents=True, exist_ok=True)
            for candidate in directory.iterdir():
                if candidate.is_file() or candidate.is_symlink():
                    try:
                        candidate.unlink()
                    except FileNotFoundError:
                        continue
                    removed += 1
        return removed

    def resolved_whisper_model(self) -> str:
        """Return a local model path or an explicitly permitted model name."""
        model_path = Path(self.whisper_model)
        required_files = {"config.json", "model.bin", "tokenizer.json"}
        if model_path.is_dir() and required_files.issubset(
            child.name for child in model_path.iterdir()
        ):
            return str(model_path.resolve())
        if self.allow_model_download and self.allow_network:
            return self.whisper_model
        raise ValueError(
            "A complete Whisper model is not available locally. Put it at "
            f"'{self.whisper_model}', or explicitly enable both "
            "JARVIS_ALLOW_MODEL_DOWNLOAD and JARVIS_ALLOW_NETWORK for the first download."
        )

    def resolved_wake_models(self) -> dict[str, Path]:
        """Resolve the local ONNX files needed for Hey Jarvis detection."""
        required = {
            "wakeword": "hey_jarvis_v0.1.onnx",
            "melspectrogram": "melspectrogram.onnx",
            "embedding": "embedding_model.onnx",
        }
        resolved = {name: self.wake_model_dir / filename for name, filename in required.items()}
        missing = [str(path) for path in resolved.values() if not path.is_file()]
        if missing:
            raise ValueError(f"Wake-word model files are missing: {', '.join(missing)}")
        return resolved

    def resolved_piper_model(self) -> Path:
        """Resolve a Piper model and its adjacent JSON configuration."""
        config_path = self.piper_model.with_suffix(self.piper_model.suffix + ".json")
        if not self.piper_model.is_file() or not config_path.is_file():
            raise ValueError(f"Piper voice model is missing: {self.piper_model}")
        return self.piper_model.resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""
    return Settings()
