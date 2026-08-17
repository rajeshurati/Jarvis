"""One-shot YOLO worker; raw image bytes enter through stdin and are never saved."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO  # type: ignore[attr-defined]


def detect(model_path: Path, confidence: float, image: bytes) -> list[dict[str, Any]]:
    """Decode an in-memory image and return JSON-compatible detections."""
    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("The object-detection image could not be decoded.")
    model = YOLO(str(model_path))
    results: Any = model.predict(frame, conf=confidence, device="cpu", verbose=False, max_det=50)
    detections: list[dict[str, Any]] = []
    for result in results:
        names = result.names
        for box in result.boxes:
            left, top, right, bottom = (round(float(value)) for value in box.xyxy[0])
            class_id = int(box.cls[0])
            detections.append(
                {
                    "label": str(names[class_id]),
                    "confidence": float(box.conf[0]),
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                }
            )
    return detections


def run() -> int:
    """Execute one bounded inference request."""
    if len(sys.argv) != 3:
        return 2
    image = sys.stdin.buffer.read(20 * 1024 * 1024 + 1)
    if len(image) > 20 * 1024 * 1024:
        return 2
    try:
        rows = detect(Path(sys.argv[1]), float(sys.argv[2]), image)
    except Exception as error:
        print(type(error).__name__, file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(rows, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
