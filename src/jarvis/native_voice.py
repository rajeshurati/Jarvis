"""Always-on voice conversation runtime for the signed-in Windows session.

The FastAPI service intentionally runs as a background process, which cannot
reliably access a Windows microphone or speakers.  This module owns audio in the
interactive desktop process and sends only transient WAV bytes to the loopback
API for local transcription, reasoning, and speech synthesis.
"""

from __future__ import annotations

import io
import json
import logging
import queue
import re
import threading
import time
import uuid
import wave
import webbrowser
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np

from jarvis.capabilities.speech import WakeWordDetector

LOGGER = logging.getLogger(__name__)


class NativeVoiceError(RuntimeError):
    """A recoverable microphone, speaker, or loopback API failure."""


@dataclass(frozen=True, slots=True)
class NativeVoiceStatus:
    """Thread-safe snapshot shown by the desktop control panel."""

    running: bool
    enabled: bool
    state: str
    last_error: str | None = None
    last_transcript: str | None = None


VoiceEventCallback = Callable[[str, str | None], None]


def execute_interactive_desktop_action(action: str) -> bool:
    """Run a small allowlisted action in the signed-in Windows desktop session."""
    try:
        import ctypes

        import pyautogui

        user32 = ctypes.windll.user32
        foreground = user32.GetForegroundWindow()
        if action == "scroll_down":
            if foreground:
                user32.ShowWindow(foreground, 3)
            pyautogui.scroll(-5)
        elif action == "scroll_up":
            if foreground:
                user32.ShowWindow(foreground, 3)
            pyautogui.scroll(5)
        elif action == "maximize_window":
            if not foreground:
                return False
            user32.ShowWindow(foreground, 3)
            user32.SetForegroundWindow(foreground)
        elif action == "minimize_window":
            if not foreground:
                return False
            user32.ShowWindow(foreground, 6)
        elif action == "close_tab":
            pyautogui.hotkey("ctrl", "w")
        elif action == "browser_back":
            pyautogui.hotkey("alt", "left")
            foreground = user32.GetForegroundWindow()
            if foreground:
                user32.ShowWindow(foreground, 3)
        else:
            return False
        return True
    except Exception:
        return False


class VoiceAPI(Protocol):
    """Small loopback API used by the interactive audio runtime."""

    def health(self) -> bool: ...

    def transcribe(self, wav_payload: bytes) -> str: ...

    def respond(self, text: str) -> str: ...

    def synthesize(self, text: str) -> bytes: ...

    def claim_due_reminders(self) -> list[str]: ...

    def enroll_speaker(self, wav_payload: bytes) -> str: ...

    def verify_speaker(self, wav_payload: bytes) -> str: ...

    def authorized_user_present(self) -> bool: ...


class AudioIO(Protocol):
    """Interactive-session microphone and speaker boundary."""

    def start(self, callback: Callable[[np.ndarray], None]) -> None: ...

    def stop(self) -> None: ...

    def play_wav(self, payload: bytes, interrupted: threading.Event) -> bool: ...


class LocalJarvisVoiceAPI:
    """Strict localhost-only HTTP client with bounded request timeouts."""

    def __init__(self, base_url: str, timeout_seconds: float = 95.0) -> None:
        normalized = base_url.rstrip("/")
        if normalized not in {"http://127.0.0.1:8765", "http://localhost:8765"} and not (
            normalized.startswith("http://127.0.0.1:")
            or normalized.startswith("http://localhost:")
        ):
            raise ValueError("Native voice API must use localhost")
        self._base_url = normalized
        self._timeout = timeout_seconds

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> bytes:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(
            f"{self._base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return cast(bytes, response.read())
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                detail = None
            raise NativeVoiceError(str(detail or f"Local API returned {error.code}")) from error
        except (OSError, URLError) as error:
            raise NativeVoiceError("Local Jarvis service is unavailable") from error

    def _json(self, path: str, body: dict[str, Any] | None = None) -> Any:
        raw = self._request(
            path,
            method="POST" if body is not None else "GET",
            body=json.dumps(body).encode("utf-8") if body is not None else None,
            content_type="application/json" if body is not None else None,
        )
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NativeVoiceError("Local Jarvis returned an invalid response") from error

    def health(self) -> bool:
        try:
            payload = self._json("/health")
            return isinstance(payload, dict) and payload.get("status") == "ok"
        except (NativeVoiceError, AttributeError):
            return False

    def transcribe(self, wav_payload: bytes) -> str:
        payload = self._upload_audio("/voice/transcribe-upload", wav_payload)
        return str(payload.get("text", "")).strip()

    def _upload_audio(self, path: str, wav_payload: bytes) -> dict[str, Any]:
        boundary = f"jarvis-{uuid.uuid4().hex}"
        header = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="audio"; filename="command.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("ascii")
        body = header + wav_payload + f"\r\n--{boundary}--\r\n".encode("ascii")
        raw = self._request(
            path,
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        try:
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError
            return payload
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError) as error:
            raise NativeVoiceError("Local audio service returned an invalid response") from error

    def respond(self, text: str) -> str:
        payload = self._json("/assistant/respond", {"text": text})
        target_url = str(payload.get("target_url") or "")
        parsed = urlparse(target_url)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "mail.google.com"
            and target_url
        ):
            webbrowser.open(target_url, new=0)
            threading.Timer(
                0.35, execute_interactive_desktop_action, args=("maximize_window",)
            ).start()
            threading.Timer(
                1.2, execute_interactive_desktop_action, args=("maximize_window",)
            ).start()
        desktop_action = str(payload.get("desktop_action") or "")
        if desktop_action:
            execute_interactive_desktop_action(desktop_action)
        elif str(payload.get("action") or "") in {
            "open_application",
            "open_website",
        }:
            threading.Timer(
                1.0, execute_interactive_desktop_action, args=("maximize_window",)
            ).start()
        return str(payload.get("reply", "")).strip()

    def synthesize(self, text: str) -> bytes:
        return self._request(
            "/assistant/speak",
            method="POST",
            body=json.dumps({"text": text}).encode("utf-8"),
            content_type="application/json",
        )

    def claim_due_reminders(self) -> list[str]:
        payload = self._json("/reminders/claim-due", {})
        if not isinstance(payload, list):
            raise NativeVoiceError("Reminder service returned an invalid response")
        return [str(item.get("title", "")).strip() for item in payload if item.get("title")]

    def enroll_speaker(self, wav_payload: bytes) -> str:
        payload = self._upload_audio("/speaker/enroll-audio?name=Rajesh", wav_payload)
        return f"Local voice recognition is enrolled for {payload.get('name', 'Rajesh')}."

    def verify_speaker(self, wav_payload: bytes) -> str:
        payload = self._upload_audio("/speaker/verify-audio", wav_payload)
        if payload.get("recognized"):
            similarity = float(payload.get("similarity") or 0)
            return (
                f"Voice recognized as {payload.get('name')}, similarity {similarity:.2f}. "
                "Voice alone does not authorize sensitive actions."
            )
        return "The current voice is not recognized."

    def authorized_user_present(self) -> bool:
        status = self._json("/identity/status")
        if not isinstance(status, dict):
            raise NativeVoiceError("Face authorization returned an invalid response")
        profiles = status.get("enrolled_profiles")
        if not profiles:
            return True
        if status.get("session_authorized"):
            return True
        result = self._json("/identity/verify-current", {})
        return isinstance(result, dict) and bool(result.get("authorized"))


class SoundDeviceAudioIO:
    """Full-duplex PortAudio adapter owned by the signed-in user session."""

    def __init__(
        self,
        *,
        sample_rate: int,
        channels: int,
        channel_index: int,
        device: int | str | None,
        frame_samples: int = 1_280,
    ) -> None:
        if not 0 <= channel_index < channels:
            raise ValueError("channel_index must be less than channels")
        self._sample_rate = sample_rate
        self._channels = channels
        self._channel_index = channel_index
        self._device = device
        self._frame_samples = frame_samples
        self._stream: Any | None = None

    @staticmethod
    def _sounddevice() -> Any:
        try:
            import sounddevice
        except ImportError as error:
            raise NativeVoiceError("The local sounddevice package is not installed") from error
        return sounddevice

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        sounddevice = self._sounddevice()

        def receive(
            data: np.ndarray,
            _frames: int,
            _time_info: Any,
            status: Any,
        ) -> None:
            if status:
                LOGGER.warning("native_voice_input_status", extra={"status": str(status)})
            callback(np.asarray(data[:, self._channel_index], dtype=np.int16).copy())

        try:
            self._stream = sounddevice.InputStream(
                samplerate=self._sample_rate,
                blocksize=self._frame_samples,
                device=self._device,
                channels=self._channels,
                dtype="int16",
                callback=receive,
            )
            self._stream.start()
        except Exception as error:
            self._stream = None
            raise NativeVoiceError("Unable to start the configured microphone") from error

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

    def play_wav(self, payload: bytes, interrupted: threading.Event) -> bool:
        sounddevice = self._sounddevice()
        try:
            with wave.open(io.BytesIO(payload), "rb") as source:
                if source.getsampwidth() != 2:
                    raise NativeVoiceError("Jarvis speech is not 16-bit PCM")
                rate = source.getframerate()
                channels = source.getnchannels()
                with sounddevice.RawOutputStream(
                    samplerate=rate, channels=channels, dtype="int16"
                ) as output:
                    block_frames = max(1, rate // 12)
                    while not interrupted.is_set():
                        block = source.readframes(block_frames)
                        if not block:
                            break
                        output.write(block)
        except NativeVoiceError:
            raise
        except Exception as error:
            raise NativeVoiceError("Unable to play Jarvis speech") from error
        return interrupted.is_set()


def encode_mono_wav(samples: list[np.ndarray], sample_rate: int) -> bytes:
    """Encode transient mono int16 chunks without writing personal audio to disk."""
    payload = np.concatenate(samples).astype("<i2", copy=False).tobytes() if samples else b""
    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(payload)
    return output.getvalue()


class NativeVoiceRuntime:
    """Wake-word state machine supporting natural follow-up and speech interruption."""

    def __init__(
        self,
        detector: WakeWordDetector,
        audio: AudioIO,
        api: VoiceAPI,
        *,
        sample_rate: int = 16_000,
        speech_threshold: float = 0.018,
        barge_threshold: float = 0.065,
        silence_threshold: float = 0.010,
        silence_frames: int = 8,
        maximum_command_frames: int = 150,
        reminder_interval_seconds: float = 2.0,
        event_callback: VoiceEventCallback | None = None,
    ) -> None:
        self._detector = detector
        self._audio = audio
        self._api = api
        self._sample_rate = sample_rate
        self._speech_threshold = speech_threshold
        self._barge_threshold = barge_threshold
        self._silence_threshold = silence_threshold
        self._silence_frames = silence_frames
        self._maximum_command_frames = maximum_command_frames
        self._reminder_interval = reminder_interval_seconds
        self._event_callback = event_callback
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=256)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._playback_interrupt = threading.Event()
        self._thread: threading.Thread | None = None
        self._reminder_thread: threading.Thread | None = None
        self._enabled = True
        self._state = "stopped"
        self._last_error: str | None = None
        self._last_transcript: str | None = None
        self._command: list[np.ndarray] = []
        self._command_changed_topic = False
        self._pre_roll: deque[np.ndarray] = deque(maxlen=5)
        self._speech_seen = False
        self._quiet_frames = 0
        self._barge_frames = 0

    def _emit_event(self, kind: str, text: str | None = None) -> None:
        callback = self._event_callback
        if callback is None:
            return
        try:
            callback(kind, text)
        except Exception:
            LOGGER.exception("native_voice_event_callback_failed")
        self._speaking_since = 0.0

    def start(self) -> None:
        """Start one microphone stream and two bounded worker threads."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._detector.reset()
            self._state = "starting"
        try:
            self._audio.start(self._on_audio)
        except Exception as error:
            self._set_error(error)
            return
        with self._lock:
            self._state = "listening"
            self._last_error = None
        self._thread = threading.Thread(
            target=self._process_audio, name="jarvis-native-voice", daemon=True
        )
        self._reminder_thread = threading.Thread(
            target=self._poll_reminders, name="jarvis-native-reminders", daemon=True
        )
        self._thread.start()
        self._reminder_thread.start()
        LOGGER.info("native_voice_started")

    def stop(self) -> None:
        self._stop.set()
        self._playback_interrupt.set()
        self._audio.stop()
        with self._lock:
            self._state = "stopped"
        LOGGER.info("native_voice_stopped")

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            if not enabled:
                self._playback_interrupt.set()
                self._state = "paused"
            elif self._state == "paused":
                while not self._frames.empty():
                    try:
                        self._frames.get_nowait()
                    except queue.Empty:
                        break
                self._detector.reset()
                self._state = "listening"

    def status(self) -> NativeVoiceStatus:
        with self._lock:
            return NativeVoiceStatus(
                running=bool(self._thread and self._thread.is_alive()),
                enabled=self._enabled,
                state=self._state,
                last_error=self._last_error,
                last_transcript=self._last_transcript,
            )

    def _set_error(self, error: Exception) -> None:
        message = str(error) or type(error).__name__
        LOGGER.exception("native_voice_error", exc_info=error)
        with self._lock:
            self._last_error = message
            self._state = "error"
        self._emit_event("error", message)

    def _on_audio(self, samples: np.ndarray) -> None:
        if self._stop.is_set() or not self._enabled:
            return
        try:
            self._frames.put_nowait(samples)
        except queue.Full:
            try:
                self._frames.get_nowait()
                self._frames.put_nowait(samples)
            except queue.Empty:
                return

    @staticmethod
    def _rms(samples: np.ndarray) -> float:
        normalized = samples.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(np.square(normalized)))) if samples.size else 0.0

    def _process_audio(self) -> None:
        while not self._stop.is_set():
            try:
                samples = self._frames.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self._process_frame(samples)
            except Exception as error:
                self._set_error(error)
                self._stop.wait(1.0)
                with self._lock:
                    if self._enabled and not self._stop.is_set():
                        self._detector.reset()
                        self._state = "listening"

    def _process_frame(self, samples: np.ndarray) -> None:
        with self._lock:
            state = self._state
        level = self._rms(samples)
        self._pre_roll.append(samples.copy())
        if state == "listening":
            detected, _score = self._detector.process_pcm(samples.astype("<i2").tobytes())
            if detected:
                self._begin_wake()
        elif state == "speaking":
            if time.monotonic() - self._speaking_since < 0.4:
                return
            self._barge_frames = self._barge_frames + 1 if level >= self._barge_threshold else 0
            if self._barge_frames >= 2:
                self._playback_interrupt.set()
                self._begin_command(list(self._pre_roll), topic_changed=True)
        elif state == "command":
            self._command.append(samples.copy())
            if level >= self._speech_threshold:
                self._speech_seen = True
                self._quiet_frames = 0
            elif self._speech_seen and level <= self._silence_threshold:
                self._quiet_frames += 1
            should_finish = (
                self._speech_seen
                and self._quiet_frames >= self._silence_frames
                and len(self._command) >= 10
            ) or len(self._command) >= self._maximum_command_frames
            if should_finish:
                self._finish_command()

    def _begin_wake(self) -> None:
        with self._lock:
            if self._state != "listening":
                return
            self._state = "speaking"
            self._speaking_since = time.monotonic()
            self._barge_frames = 0
            self._playback_interrupt.clear()
        self._emit_event("wake", "Hey Jarvis")
        threading.Thread(target=self._acknowledge, name="jarvis-wake-reply", daemon=True).start()

    def _acknowledge(self) -> None:
        try:
            self._speak("Yes?")
            with self._lock:
                if self._state == "speaking":
                    self._begin_command([])
        except Exception as error:
            self._set_error(error)

    def _begin_command(
        self, initial: list[np.ndarray], *, topic_changed: bool = False
    ) -> None:
        with self._lock:
            self._state = "command"
            self._command = [item.copy() for item in initial]
            self._command_changed_topic = topic_changed
            self._speech_seen = bool(initial)
            self._quiet_frames = 0
            self._barge_frames = 0

    def _finish_command(self) -> None:
        with self._lock:
            if self._state != "command":
                return
            samples = self._command
            topic_changed = self._command_changed_topic
            self._command = []
            self._command_changed_topic = False
            self._state = "thinking"
        threading.Thread(
            target=self._handle_command,
            args=(samples, topic_changed),
            name="jarvis-command",
            daemon=True,
        ).start()

    def _handle_command(self, samples: list[np.ndarray], topic_changed: bool) -> None:
        try:
            wav_payload = encode_mono_wav(samples, self._sample_rate)
            transcript = self._api.transcribe(wav_payload)
            with self._lock:
                self._last_transcript = transcript or None
            if transcript:
                self._emit_event("transcript", transcript)
            if not transcript:
                self._resume_listening()
                return
            normalized = re.sub(r"\s+", " ", transcript.casefold()).strip(" .!?")
            face_enrollment = (
                "face" in normalized
                and any(
                    term in normalized
                    for term in ("enroll", "register", "scan", "add", "save")
                )
            ) or normalized in {"enroll me", "register me"}
            if not face_enrollment and not self._api.authorized_user_present():
                reply = "I cannot verify an authorized user in front of the camera."
            elif normalized in {"enroll my voice", "register my voice", "enroll speaker"}:
                reply = self._api.enroll_speaker(wav_payload)
            elif normalized in {"recognize my voice", "who is speaking", "verify speaker"}:
                reply = self._api.verify_speaker(wav_payload)
            else:
                current_intent = f"Actually, {transcript}" if topic_changed else transcript
                reply = self._api.respond(current_intent)
            if not reply:
                reply = "I completed that without a spoken response."
            self._emit_event("response", reply)
            with self._lock:
                self._state = "speaking"
                self._speaking_since = time.monotonic()
                self._barge_frames = 0
                self._playback_interrupt.clear()
            interrupted = self._speak(reply)
            with self._lock:
                if self._state == "speaking" and not interrupted:
                    self._begin_command([])
        except Exception as error:
            self._set_error(error)
            self._resume_listening(delay=1.0)

    def _speak(self, text: str) -> bool:
        return self._audio.play_wav(self._api.synthesize(text[:2_000]), self._playback_interrupt)

    def _resume_listening(self, delay: float = 0.0) -> None:
        if delay:
            self._stop.wait(delay)
        with self._lock:
            if not self._stop.is_set() and self._enabled:
                self._detector.reset()
                self._state = "listening"

    def _poll_reminders(self) -> None:
        while not self._stop.wait(self._reminder_interval):
            with self._lock:
                available = self._enabled and self._state == "listening"
            if not available or not self._api.health():
                continue
            try:
                reminders = self._api.claim_due_reminders()
                for title in reminders:
                    if self._stop.is_set():
                        return
                    with self._lock:
                        if self._state != "listening":
                            break
                        self._state = "speaking"
                        self._speaking_since = time.monotonic()
                        self._barge_frames = 0
                        self._playback_interrupt.clear()
                    self._speak(f"Reminder: {title}")
                    self._emit_event("reminder", title)
                    with self._lock:
                        still_speaking = self._state == "speaking"
                    if still_speaking:
                        self._resume_listening()
            except Exception as error:
                LOGGER.warning("native_reminder_delivery_failed", extra={"error": str(error)})
