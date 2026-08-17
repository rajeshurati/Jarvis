"""Atomic local storage for derived speaker embeddings."""

from __future__ import annotations

import json
from pathlib import Path

from jarvis.capabilities.identity import IdentityError


class JsonSpeakerProfileStore:
    """Store bounded voiceprints in a private, user-deletable JSON file."""

    def __init__(self, path: Path, max_samples: int = 5) -> None:
        self._path = path
        self._max_samples = max_samples

    def profiles(self) -> dict[str, list[list[float]]]:
        if not self._path.is_file():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            profiles = payload.get("profiles", {})
            if not isinstance(profiles, dict):
                raise TypeError
            return {
                str(name): [[float(value) for value in sample] for sample in samples]
                for name, samples in profiles.items()
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise IdentityError("The local speaker profile store is invalid.") from error

    def add_sample(self, name: str, embedding: list[float]) -> None:
        normalized_name = name.strip()
        if not normalized_name or not embedding:
            raise ValueError("A name and speaker embedding are required")
        profiles = self.profiles()
        samples = profiles.setdefault(normalized_name, [])
        samples.append([float(value) for value in embedding])
        profiles[normalized_name] = samples[-self._max_samples :]
        self._save(profiles)

    def delete(self, name: str) -> bool:
        profiles = self.profiles()
        existing = next((item for item in profiles if item.casefold() == name.casefold()), None)
        if existing is None:
            return False
        del profiles[existing]
        self._save(profiles)
        return True

    def _save(self, profiles: dict[str, list[list[float]]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "profiles": profiles}, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self._path)
