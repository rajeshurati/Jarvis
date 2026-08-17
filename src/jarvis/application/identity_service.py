"""Local biometric enrollment and short-lived authorization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from jarvis.capabilities.identity import (
    Camera,
    FaceEmbeddingEngine,
    FaceProfileStore,
    IdentityError,
    IdentityResult,
)


class FaceAuthorizationService:
    """Authorize a current face against locally stored normalized embeddings."""

    def __init__(
        self,
        engine: FaceEmbeddingEngine,
        profiles: FaceProfileStore,
        camera: Camera,
        threshold: float = 0.45,
        session_minutes: int = 5,
    ) -> None:
        self._engine = engine
        self._profiles = profiles
        self._camera = camera
        self._threshold = threshold
        self._session_minutes = session_minutes
        self._authorized_name: str | None = None
        self._authorized_until: datetime | None = None

    def profile_names(self) -> list[str]:
        """List enrolled profile names without exposing embeddings."""
        return sorted(self._profiles.profiles())

    def is_session_authorized(self) -> bool:
        """Return whether a recent face match is still valid."""
        return bool(
            self._authorized_name
            and self._authorized_until
            and datetime.now(UTC) < self._authorized_until
        )

    def enroll_current(self, name: str) -> IdentityResult:
        """Enroll one explicitly requested current webcam face."""
        return self.enroll(name, self._camera.capture_jpeg())

    def enroll(self, name: str, image: bytes) -> IdentityResult:
        """Store exactly one normalized face embedding and discard the image."""
        embeddings = self._engine.extract(image)
        if len(embeddings) != 1:
            status = "no_face" if not embeddings else "multiple_faces"
            raise IdentityError(f"Enrollment requires exactly one face; status: {status}.")
        self._profiles.add_sample(name, embeddings[0])
        self._authorize(name)
        return IdentityResult("enrolled", True, name.strip(), 1.0, 1)

    def verify_current(self) -> IdentityResult:
        """Verify a transient webcam frame."""
        return self.verify(self._camera.capture_jpeg())

    def faces_current(self) -> int:
        """Count current faces without storing the frame or requiring enrollment."""
        return len(self._engine.extract(self._camera.capture_jpeg()))

    def verify(self, image: bytes) -> IdentityResult:
        """Compare every detected face with every enrolled sample."""
        profiles = self._profiles.profiles()
        if not profiles:
            return IdentityResult("not_enrolled", False, None, None, 0)
        embeddings = self._engine.extract(image)
        if not embeddings:
            return IdentityResult("no_face", False, None, None, 0)
        best_name: str | None = None
        best_similarity = -1.0
        for candidate in embeddings:
            candidate_vector = np.asarray(candidate, dtype=np.float32)
            for name, samples in profiles.items():
                for sample in samples:
                    similarity = float(np.dot(candidate_vector, np.asarray(sample)))
                    if similarity > best_similarity:
                        best_name, best_similarity = name, similarity
        authorized = best_name is not None and best_similarity >= self._threshold
        if authorized and best_name:
            self._authorize(best_name)
        return IdentityResult(
            "authorized" if authorized else "unauthorized",
            authorized,
            best_name if authorized else None,
            round(best_similarity, 4),
            len(embeddings),
        )

    def delete_profile(self, name: str) -> bool:
        """Delete one explicitly selected profile and revoke its session."""
        deleted = self._profiles.delete(name)
        if (
            deleted
            and self._authorized_name
            and self._authorized_name.casefold() == name.casefold()
        ):
            self._authorized_name = None
            self._authorized_until = None
        return deleted

    def _authorize(self, name: str) -> None:
        self._authorized_name = name.strip()
        self._authorized_until = datetime.now(UTC) + timedelta(minutes=self._session_minutes)
