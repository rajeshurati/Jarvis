"""Transient webcam object recognition."""

from __future__ import annotations

from collections import Counter

from jarvis.capabilities.identity import Camera, IdentityError
from jarvis.capabilities.vision import ObjectDetector


class ObjectRecognitionService:
    """Capture one frame, detect locally, and immediately discard raw pixels."""

    def __init__(self, camera: Camera, detector: ObjectDetector) -> None:
        self._camera = camera
        self._detector = detector

    def describe_current(self) -> str:
        """Describe counts of confidently detected objects."""
        try:
            detections = self._detector.detect(self._camera.capture_jpeg())
        except (IdentityError, RuntimeError) as error:
            raise RuntimeError("Local webcam object recognition is unavailable.") from error
        if not detections:
            return "I do not detect a recognized object in the current webcam view."
        counts = Counter(item.label for item in detections)
        summary = ", ".join(
            f"{count} {label}{'' if count == 1 else 's'}"
            for label, count in counts.most_common(10)
        )
        return f"I can see {summary}."
