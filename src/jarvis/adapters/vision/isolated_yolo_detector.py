"""Memory-isolated local Ultralytics YOLO object detector."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from jarvis.capabilities.vision import DetectedObject


class IsolatedYOLOObjectDetector:
    """Run YOLO in a short-lived worker so model memory is always released."""

    def __init__(
        self, model_path: Path, confidence: float = 0.35, timeout_seconds: float = 90.0
    ) -> None:
        if not model_path.is_file():
            raise ValueError(f"Local YOLO model is missing: {model_path}")
        self._model_path = model_path.resolve()
        self._confidence = confidence
        self._timeout_seconds = timeout_seconds

    def detect(self, image: bytes) -> list[DetectedObject]:
        """Analyze one in-memory image in an isolated local process."""
        if not image or len(image) > 20 * 1024 * 1024:
            raise RuntimeError("The object-detection image is invalid.")
        environment = os.environ.copy()
        config_directory = self._model_path.parent / ".ultralytics"
        config_directory.mkdir(parents=True, exist_ok=True)
        environment["YOLO_CONFIG_DIR"] = str(config_directory)
        environment["MPLCONFIGDIR"] = str(config_directory)
        command = (
            sys.executable,
            "-m",
            "jarvis.adapters.vision.yolo_worker",
            str(self._model_path),
            str(self._confidence),
        )
        try:
            result = subprocess.run(
                command,
                input=image,
                capture_output=True,
                timeout=self._timeout_seconds,
                check=True,
                env=environment,
            )
            rows = json.loads(result.stdout.decode("utf-8"))
        except (
            OSError,
            subprocess.SubprocessError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError("Local object detection failed.") from error
        if not isinstance(rows, list):
            raise RuntimeError("Local object detection returned invalid data.")
        detections: list[DetectedObject] = []
        for row in rows[:50]:
            if not isinstance(row, dict):
                raise RuntimeError("Local object detection returned invalid data.")
            try:
                detections.append(
                    DetectedObject(
                        label=str(row["label"]),
                        confidence=float(row["confidence"]),
                        left=int(row["left"]),
                        top=int(row["top"]),
                        right=int(row["right"]),
                        bottom=int(row["bottom"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("Local object detection returned invalid data.") from error
        return sorted(detections, key=lambda item: item.confidence, reverse=True)
