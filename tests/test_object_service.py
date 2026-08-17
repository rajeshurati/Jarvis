"""Transient webcam object-recognition tests."""

from jarvis.application.object_service import ObjectRecognitionService
from jarvis.capabilities.vision import DetectedObject


class StubCamera:
    def capture_jpeg(self) -> bytes:
        return b"jpeg"


class StubDetector:
    def __init__(self, detections: list[DetectedObject]) -> None:
        self.detections = detections

    def detect(self, image: bytes) -> list[DetectedObject]:
        assert image == b"jpeg"
        return self.detections


def test_object_service_summarizes_counts() -> None:
    service = ObjectRecognitionService(
        StubCamera(),
        StubDetector(
            [
                DetectedObject("person", 0.9, 0, 0, 10, 10),
                DetectedObject("person", 0.8, 20, 0, 30, 10),
                DetectedObject("laptop", 0.7, 5, 5, 15, 15),
            ]
        ),
    )

    assert service.describe_current() == "I can see 2 persons, 1 laptop."


def test_object_service_handles_no_detections() -> None:
    service = ObjectRecognitionService(StubCamera(), StubDetector([]))
    assert "do not detect" in service.describe_current()
