"""InsightFace face detection and recognition through local ONNX Runtime."""

from __future__ import annotations

from threading import Lock
from typing import Any

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from jarvis.capabilities.identity import IdentityError


class InsightFaceEmbeddingEngine:
    """Lazily load the official detection and recognition ONNX models."""

    def __init__(self, model_root: str, model_name: str = "buffalo_l") -> None:
        self._model_root = model_root
        self._model_name = model_name
        self._analysis: Any | None = None
        self._lock = Lock()

    def _model(self) -> Any:
        if self._analysis is not None:
            return self._analysis
        with self._lock:
            if self._analysis is None:
                try:
                    analysis = FaceAnalysis(
                        name=self._model_name,
                        root=self._model_root,
                        allowed_modules=["detection", "recognition"],
                        providers=["CPUExecutionProvider"],
                    )
                    analysis.prepare(ctx_id=-1, det_size=(640, 640))
                    self._analysis = analysis
                except Exception as error:
                    raise IdentityError("Local InsightFace models could not be loaded.") from error
        return self._analysis

    def extract(self, image: bytes) -> list[list[float]]:
        """Decode one image and return normalized embeddings for confident faces."""
        frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise IdentityError("The face image could not be decoded.")
        try:
            faces = self._model().get(frame)
        except Exception as error:
            raise IdentityError("Local face analysis failed.") from error
        embeddings: list[list[float]] = []
        for face in faces:
            if float(face.det_score) >= 0.6:
                embeddings.append(np.asarray(face.normed_embedding, dtype=np.float32).tolist())
        return embeddings
