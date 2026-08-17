"""Transient Windows webcam capture."""

from __future__ import annotations

import time

import cv2

from jarvis.capabilities.identity import IdentityError


class OpenCVCamera:
    """Capture a warmed-up frame without retaining it."""

    def __init__(self, device_index: int = 0) -> None:
        self._device_index = device_index

    def capture_jpeg(self) -> bytes:
        """Open the camera, warm it up, and return an in-memory JPEG."""
        camera = cv2.VideoCapture(self._device_index, cv2.CAP_DSHOW)
        try:
            if not camera.isOpened():
                raise IdentityError("The webcam is unavailable.")
            frame = None
            success = False
            for _ in range(15):
                success, frame = camera.read()
                time.sleep(0.04)
            if not success or frame is None:
                raise IdentityError("The webcam did not return an image.")
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not encoded:
                raise IdentityError("The webcam image could not be encoded.")
            return bytes(buffer)
        finally:
            camera.release()
