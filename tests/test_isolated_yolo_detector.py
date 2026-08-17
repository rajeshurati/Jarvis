from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from jarvis.adapters.vision.isolated_yolo_detector import IsolatedYOLOObjectDetector


def detector(tmp_path: Path) -> IsolatedYOLOObjectDetector:
    model = tmp_path / "yolo.pt"
    model.write_bytes(b"weights")
    return IsolatedYOLOObjectDetector(model)


def test_detector_uses_memory_only_worker_and_sorts_results(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[dict[str, Any]] = []
    rows = [
        {"label": "cup", "confidence": 0.6, "left": 1, "top": 2, "right": 3, "bottom": 4},
        {"label": "person", "confidence": 0.9, "left": 5, "top": 6, "right": 7, "bottom": 8},
    ]

    def run(command: object, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, json.dumps(rows).encode(), b"")

    monkeypatch.setattr("jarvis.adapters.vision.isolated_yolo_detector.subprocess.run", run)

    result = detector(tmp_path).detect(b"jpeg bytes")

    assert [item.label for item in result] == ["person", "cup"]
    assert calls[0]["input"] == b"jpeg bytes"
    assert calls[0]["capture_output"] is True
    assert "YOLO_CONFIG_DIR" in calls[0]["env"]


def test_detector_rejects_empty_and_invalid_worker_output(tmp_path: Path, monkeypatch: Any) -> None:
    service = detector(tmp_path)
    with pytest.raises(RuntimeError, match="invalid"):
        service.detect(b"")
    monkeypatch.setattr(
        "jarvis.adapters.vision.isolated_yolo_detector.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, b"{}", b""),
    )
    with pytest.raises(RuntimeError, match="invalid data"):
        service.detect(b"jpeg")
