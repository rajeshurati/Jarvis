"""Lazy local Ultralytics YOLO object detector."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any

import cv2
import numpy as np

from jarvis.capabilities.vision import DetectedObject


class LocalYOLOObjectDetector:
    """Load user-supplied YOLO weights locally and return bounded detections."""

    def __init__(self, model_path: Path, confidence: float = 0.35) -> None:
        if not model_path.is_file():
            raise ValueError(f"Local YOLO model is missing: {model_path}")
        self._model_path = model_path
        self._confidence = confidence
        self._instance: Any | None = None
        self._lock = Lock()

    def _model(self) -> Any:
        if self._instance is not None:
            return self._instance
        with self._lock:
            if self._instance is None:
                try:
                    config_directory = self._model_path.parent / ".ultralytics"
                    config_directory.mkdir(parents=True, exist_ok=True)
                    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_directory.resolve()))
                    os.environ.setdefault("MPLCONFIGDIR", str(config_directory.resolve()))
                    from ultralytics import YOLO  # type: ignore[attr-defined]

                    self._instance = YOLO(str(self._model_path.resolve()))
                except Exception as error:
                    raise RuntimeError("The local YOLO model could not be loaded.") from error
        return self._instance

    def detect(self, image: bytes) -> list[DetectedObject]:
        """Decode and analyze one transient webcam image on CPU."""
        frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("The object-detection image could not be decoded.")
        try:
            results = self._model().predict(
                frame, conf=self._confidence, device="cpu", verbose=False, max_det=50
            )
        except Exception as error:
            raise RuntimeError("Local object detection failed.") from error
        detections: list[DetectedObject] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                left, top, right, bottom = (round(float(value)) for value in box.xyxy[0])
                detections.append(
                    DetectedObject(
                        str(names[class_id]), confidence, left, top, right, bottom
                    )
                )
        return sorted(detections, key=lambda item: item.confidence, reverse=True)
