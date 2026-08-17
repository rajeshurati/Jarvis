"""Windows screen capture through MSS."""

from __future__ import annotations

import ctypes
from io import BytesIO

from mss import mss
from mss.tools import to_png
from PIL import ImageGrab

from jarvis.capabilities.vision import ScreenCaptureError


class MssScreenCapturer:
    """Capture all attached monitors into an in-memory PNG."""

    def capture_png(self) -> bytes:
        """Capture the virtual desktop and convert BGRA pixels to PNG."""
        image, _, _ = self.capture_png_with_origin()
        return image

    def capture_png_with_origin(self) -> tuple[bytes, int, int]:
        """Capture the desktop and preserve multi-monitor global coordinates."""
        try:
            with mss() as capture:
                monitor = capture.monitors[0]
                shot = capture.grab(monitor)
                image = to_png(shot.rgb, shot.size)
                if image is None:
                    raise ScreenCaptureError("Screen encoding returned no image.")
                return image, int(monitor["left"]), int(monitor["top"])
        except Exception:
            try:
                screenshot = ImageGrab.grab(all_screens=True)
                stream = BytesIO()
                screenshot.save(stream, format="PNG")
                user32 = ctypes.windll.user32
                left = int(user32.GetSystemMetrics(76))
                top = int(user32.GetSystemMetrics(77))
                return stream.getvalue(), left, top
            except Exception as fallback_error:
                raise ScreenCaptureError(
                    "I could not capture the current interactive Windows desktop."
                ) from fallback_error
