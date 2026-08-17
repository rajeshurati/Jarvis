"""Native Windows tray and status control surface for Local Jarvis."""

from __future__ import annotations

import html
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import cv2
from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QDir,
    QEasingCurve,
    QIODevice,
    QLockFile,
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from jarvis import __version__
from jarvis.adapters.speech.openwakeword_detector import OpenWakeWordDetector
from jarvis.core.config import get_settings
from jarvis.native_voice import (
    LocalJarvisVoiceAPI,
    NativeVoiceRuntime,
    SoundDeviceAudioIO,
    execute_interactive_desktop_action,
)


class VoiceEventBridge(QObject):
    """Move native voice events safely onto the Qt UI thread."""

    voice_event = Signal(str, object)


class InteractiveCameraPublisher(threading.Thread):
    """Publish transient webcam frames from the signed-in desktop session."""

    def __init__(self, base_url: str, camera_index: int, interval_seconds: float = 10) -> None:
        super().__init__(name="jarvis-camera-publisher", daemon=True)
        self._url = f"{base_url.rstrip('/')}/camera/snapshot"
        self._camera_index = camera_index
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._enabled = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def set_enabled(self, enabled: bool) -> None:
        """Keep the camera open only while room monitoring is enabled."""
        if enabled:
            self._enabled.set()
        else:
            self._enabled.clear()

    def run(self) -> None:
        camera: cv2.VideoCapture | None = None
        next_publish = 0.0
        try:
            while not self._stop_event.is_set():
                if not self._enabled.is_set():
                    if camera is not None:
                        camera.release()
                        camera = None
                    self._stop_event.wait(0.25)
                    continue
                if camera is None:
                    camera = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
                    if not camera.isOpened():
                        camera.release()
                        camera = None
                        self._stop_event.wait(2.0)
                        continue
                    next_publish = 0.0
                success, frame = camera.read()
                if not success or frame is None:
                    camera.release()
                    camera = None
                    self._stop_event.wait(1.0)
                    continue
                now = time.monotonic()
                if now >= next_publish:
                    self._publish_frame(frame)
                    next_publish = now + self._interval
                self._stop_event.wait(0.1)
        finally:
            if camera is not None:
                camera.release()

    def _publish_frame(self, frame: Any) -> None:
        encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not encoded:
            return
        request = Request(
            self._url,
            data=bytes(buffer),
            headers={"Content-Type": "image/jpeg"},
            method="PUT",
        )
        try:
            with urlopen(request, timeout=5):
                pass
        except OSError:
            return


class JarvisWindow(QMainWindow):
    """Small non-technical dashboard backed only by the loopback API."""

    def __init__(
        self,
        base_url: str,
        camera_index: int,
        managed_supervisor: subprocess.Popen[bytes] | None = None,
    ) -> None:
        super().__init__()
        settings = get_settings()
        self._base_url = base_url.rstrip("/")
        self._network = QNetworkAccessManager(self)
        self._presence_enabled = False
        self._really_quit = False
        self._managed_supervisor = managed_supervisor
        self._last_transcript = ""
        self._visual_state = "starting"
        self._wave_frame = 0
        self._bridge = VoiceEventBridge(self)
        self._bridge.voice_event.connect(self._handle_voice_event)
        self._camera_publisher = InteractiveCameraPublisher(base_url, camera_index)
        self._camera_publisher.start()
        wake_models = settings.resolved_wake_models()
        self._voice_runtime = NativeVoiceRuntime(
            OpenWakeWordDetector(
                wakeword_model=wake_models["wakeword"],
                melspectrogram_model=wake_models["melspectrogram"],
                embedding_model=wake_models["embedding"],
                threshold=settings.wake_threshold,
            ),
            SoundDeviceAudioIO(
                sample_rate=settings.audio_sample_rate,
                channels=settings.audio_channels,
                channel_index=settings.audio_channel_index,
                device=settings.audio_device_name or settings.audio_device_index,
            ),
            LocalJarvisVoiceAPI(base_url, settings.ollama_timeout_seconds + 10),
            sample_rate=settings.audio_sample_rate,
            event_callback=lambda kind, text: self._bridge.voice_event.emit(kind, text),
        )
        self._voice_runtime.start()
        self.setWindowTitle(f"Local Jarvis {__version__}")
        self.setMinimumSize(920, 680)
        self._build_interface()
        self._build_tray()
        self._timer = QTimer(self)
        self._timer.setInterval(5_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def _build_interface(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        self._logo_path = Path(__file__).parent / "assets" / "jarvis-orb-v1.png"
        self._logo = QLabel()
        self._logo.setObjectName("orb")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setFixedHeight(245)
        logo_pixmap = QPixmap(str(self._logo_path))
        self._logo.setPixmap(
            logo_pixmap.scaled(
                230,
                230,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._logo_glow = QGraphicsDropShadowEffect(self._logo)
        self._logo_glow.setOffset(0, 0)
        self._logo_glow.setBlurRadius(28)
        self._logo_glow.setColor("#27d7ff")
        self._logo.setGraphicsEffect(self._logo_glow)
        self._pulse = QPropertyAnimation(self._logo_glow, b"blurRadius", self)
        self._pulse.setDuration(900)
        self._pulse.setStartValue(18.0)
        self._pulse.setEndValue(54.0)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)
        layout.addWidget(self._logo)

        title = QLabel("J . A . R . V . I . S")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Your hands-free desktop assistant")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._waveform = QLabel("·  ·  ·  ·  ·")
        self._waveform.setObjectName("waveform")
        self._waveform.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._waveform)
        self._wave_timer = QTimer(self)
        self._wave_timer.setInterval(120)
        self._wave_timer.timeout.connect(self._animate_waveform)

        self._hero = QLabel('Starting — say “Hey Jarvis” when ready')
        self._hero.setObjectName("hero")
        self._hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hero)

        self._conversation = QTextBrowser()
        self._conversation.setObjectName("conversation")
        self._conversation.setOpenExternalLinks(True)
        self._conversation.setHtml(
            "<div><b>Jarvis is starting.</b><br>When the status says Listening, "
            "say <i>Hey Jarvis</i> and your request.</div>"
        )
        layout.addWidget(self._conversation, 1)

        command_row = QHBoxLayout()
        self._command_input = QLineEdit()
        self._command_input.setPlaceholderText("Type a command if you do not want to speak…")
        self._command_input.returnPressed.connect(self.submit_typed_command)
        send_button = QPushButton("Ask Jarvis")
        send_button.clicked.connect(self.submit_typed_command)
        self._gmail_button = QPushButton("Open Gmail inbox")
        self._gmail_button.clicked.connect(self.open_gmail)
        self._gmail_button.hide()
        command_row.addWidget(self._command_input, 1)
        command_row.addWidget(send_button)
        command_row.addWidget(self._gmail_button)
        layout.addLayout(command_row)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        self._health = QLabel("● Connecting to Jarvis…")
        self._presence = QLabel("Room monitoring: checking…")
        self._speaker = QLabel("Voice identity: checking…")
        self._models = QLabel("Local models: checking…")
        self._voice = QLabel("Background voice: starting...")
        for label in (self._health, self._voice, self._presence, self._speaker, self._models):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setMinimumHeight(22)
            card_layout.addWidget(label)
        layout.addWidget(card)

        actions = QHBoxLayout()
        voice_button = QPushButton("Listening diagnostics")
        voice_button.clicked.connect(self.open_voice)
        self._voice_button = QPushButton("Pause background listening")
        self._voice_button.clicked.connect(self.toggle_voice)
        self._presence_button = QPushButton("Pause room monitoring")
        self._presence_button.clicked.connect(self.toggle_presence)
        actions.addWidget(voice_button)
        actions.addWidget(self._voice_button)
        actions.addWidget(self._presence_button)
        layout.addLayout(actions)

        details_button = QPushButton("Manage memory, projects, and reminders")
        details_button.clicked.connect(self.open_control_center)
        layout.addWidget(details_button)
        api_button = QPushButton("Open technical API")
        api_button.clicked.connect(self.open_api_docs)
        layout.addWidget(api_button)

        privacy = QLabel(
            "Jarvis starts with Windows and listens locally. Email sending and other "
            "consequential actions still require your confirmation."
        )
        privacy.setWordWrap(True)
        privacy.setObjectName("privacy")
        layout.addWidget(privacy)
        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QWidget { background: #02060b; color: #edf8ff; font: 11pt 'Segoe UI'; }
            QLabel { background: transparent; }
            QLabel#orb { background: transparent; }
            QLabel#title { font-size: 27pt; font-weight: 700; color: #73ddff;
                           letter-spacing: 3px; }
            QLabel#subtitle, QLabel#privacy { color: #a8b3cf; }
            QLabel#waveform { color: #44d9ff; font: 20pt 'Consolas'; padding: 0; }
            QLabel#hero { background: #061922; border: 1px solid #199bc0;
                          border-radius: 14px; color: #b8f3ff; font-size: 16pt;
                          font-weight: 700; padding: 16px; }
            QFrame#card { background: #07111e; border: 1px solid #163b55;
                          border-radius: 12px; padding: 12px; }
            QTextBrowser#conversation { background: #040b14; border: 1px solid #16445f;
                          border-radius: 12px; padding: 16px; font-size: 12pt; }
            QLineEdit { background: #07111e; border: 1px solid #23617e; border-radius: 9px;
                        padding: 12px; color: #f4f8ff; }
            QPushButton { background: #27c8ea; color: #021017; border: 0;
                          border-radius: 8px; padding: 12px; font-weight: 600; }
            QPushButton:hover { background: #76e8ff; }
            """
        )
        self._set_visual_state("starting")

    @Slot()
    def _animate_waveform(self) -> None:
        frames = (
            "▁ ▂ ▃ ▅ ▇ ▅ ▃ ▂ ▁",
            "▂ ▄ ▆ █ ▆ ▄ ▂ ▃ ▅",
            "▃ ▆ ▄ ▇ █ ▅ ▂ ▄ ▃",
            "▁ ▃ ▅ ▇ ▅ ▃ ▁ ▄ ▆",
        )
        self._waveform.setText(frames[self._wave_frame % len(frames)])
        self._wave_frame += 1

    def _set_visual_state(self, state: str) -> None:
        """Animate the HUD to match the live voice state."""
        if state == self._visual_state and state not in {"starting"}:
            return
        self._visual_state = state
        colors = {
            "listening": "#25d9ff",
            "command": "#59f5ff",
            "thinking": "#9b8cff",
            "speaking": "#ff4058",
            "error": "#ff9a45",
            "paused": "#617083",
            "ready": "#29ddb5",
            "starting": "#27d7ff",
        }
        self._logo_glow.setColor(colors.get(state, "#27d7ff"))
        active = state in {"listening", "command", "thinking", "speaking", "starting"}
        if active:
            if self._pulse.state() != QPropertyAnimation.State.Running:
                self._pulse.start()
            if not self._wave_timer.isActive():
                self._wave_timer.start()
        else:
            self._pulse.stop()
            self._logo_glow.setBlurRadius(24)
            self._wave_timer.stop()
            self._waveform.setText("·  ·  ·  ·  ·")

    def _build_tray(self) -> None:
        icon = QIcon(str(self._logo_path))
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self._tray = QSystemTrayIcon(QIcon(icon), self)
        self._tray.setToolTip("Local Jarvis")
        menu = QMenu()
        show_action = QAction("Open Jarvis", self)
        show_action.triggered.connect(self.show_and_raise)
        voice_action = QAction("Voice conversation", self)
        voice_action.triggered.connect(self.open_voice)
        quit_action = QAction("Quit control panel", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(show_action)
        menu.addAction(voice_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    @Slot()
    def refresh(self) -> None:
        self._refresh_native_voice()
        self._publish_screen_snapshot()
        self._request("health", "/health")
        self._request("presence", "/presence/status")
        self._request("speaker", "/speaker/status")
        self._request("diagnostics", "/diagnostics")

    def _refresh_native_voice(self) -> None:
        status = self._voice_runtime.status()
        request = QNetworkRequest(QUrl(f"{self._base_url}/voice/runtime-status"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        payload = json.dumps(
            {
                "running": status.running,
                "enabled": status.enabled,
                "state": status.state,
                "last_error": status.last_error,
            }
        ).encode("utf-8")
        reply = self._network.put(request, payload)
        reply.finished.connect(reply.deleteLater)
        if status.last_error:
            self._set_visual_state("error")
            self._voice.setText(f"Background voice: needs attention - {status.last_error}")
            self._voice.setStyleSheet("color: #ffb86b")
        elif status.enabled and status.running:
            self._set_visual_state(status.state)
            readable = {
                "listening": 'listening for "Hey Jarvis"',
                "command": "listening to you",
                "thinking": "thinking locally",
                "speaking": "speaking - interrupt anytime",
            }.get(status.state, status.state)
            self._voice.setText(f"Background voice: {readable}")
            self._voice.setStyleSheet("color: #72e6a6")
            self._hero.setText(readable.capitalize())
        else:
            self._set_visual_state("paused")
            self._voice.setText("Background voice: paused")
            self._voice.setStyleSheet("color: #a8b3cf")
        self._voice_button.setText(
            "Pause background listening" if status.enabled else "Resume background listening"
        )

    def _publish_screen_snapshot(self) -> None:
        """Send the current interactive screen to the in-memory localhost cache."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.geometry()
        pixmap = screen.grabWindow(0)
        payload = QByteArray()
        buffer = QBuffer(payload)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            return
        try:
            if not pixmap.save(buffer, "PNG"):
                return
        finally:
            buffer.close()
        request = QNetworkRequest(QUrl(f"{self._base_url}/screen/snapshot"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "image/png")
        request.setRawHeader(b"X-Screen-Left", str(geometry.left()).encode("ascii"))
        request.setRawHeader(b"X-Screen-Top", str(geometry.top()).encode("ascii"))
        reply = self._network.put(request, bytes(payload.data()))
        reply.finished.connect(reply.deleteLater)

    def _request(self, kind: str, path: str, *, post: bool = False) -> None:
        request = QNetworkRequest(QUrl(f"{self._base_url}{path}"))
        reply = self._network.post(request, b"") if post else self._network.get(request)
        reply.setProperty("jarvis_kind", kind)
        reply.finished.connect(self._reply_finished)

    @Slot()
    def _reply_finished(self) -> None:
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return
        kind = str(reply.property("jarvis_kind"))
        if reply.error() != QNetworkReply.NetworkError.NoError:
            if kind == "health":
                self._health.setText("● Jarvis is offline — the supervisor will retry")
                self._health.setStyleSheet("color: #ff8a8a")
            reply.deleteLater()
            return
        try:
            body = bytes(reply.readAll().data()).decode("utf-8")
            payload: dict[str, Any] = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            reply.deleteLater()
            return
        self._apply_status(kind, payload)
        reply.deleteLater()

    def _apply_status(self, kind: str, payload: dict[str, Any]) -> None:
        if kind == "health":
            self._health.setText(f"● Jarvis is ready · version {payload.get('version', '?')}")
            self._health.setStyleSheet("color: #72e6a6")
        elif kind == "presence":
            self._presence_enabled = bool(payload.get("enabled"))
            self._camera_publisher.set_enabled(self._presence_enabled)
            state = "active" if self._presence_enabled else "paused"
            camera_note = "camera on" if self._presence_enabled else "camera off"
            self._presence.setText(f"Room monitoring: {state} - {camera_note}")
            self._presence_button.setText(
                "Pause room monitoring" if self._presence_enabled else "Resume room monitoring"
            )
        elif kind == "speaker":
            available = bool(payload.get("available"))
            profiles = payload.get("enrolled_profiles") or []
            if not available:
                text = "Voice identity: model unavailable"
            elif profiles:
                text = f"Voice identity: enrolled for {', '.join(map(str, profiles))}"
            else:
                text = 'Voice identity: ready — say "Enroll my voice"'
            self._speaker.setText(text)
        elif kind == "diagnostics":
            names = [str(item.get("name", "")) for item in payload.get("models", [])]
            text_model = str(payload.get("configured_text_model", "?"))
            vision_model = str(payload.get("configured_vision_model", "?"))
            installed = "ready" if text_model in names and vision_model in names else "incomplete"
            self._models.setText(
                f"Local models: {installed} · chat {text_model} · vision {vision_model}"
            )
        elif kind == "manual_response":
            response = str(payload.get("reply") or "Jarvis completed the request.")
            target_url = str(payload.get("target_url") or "")
            target = QUrl(target_url)
            if target.scheme() == "https" and target.host() == "mail.google.com":
                QDesktopServices.openUrl(target)
                QTimer.singleShot(
                    1_000, lambda: execute_interactive_desktop_action("maximize_window")
                )
            desktop_action = str(payload.get("desktop_action") or "")
            if desktop_action:
                execute_interactive_desktop_action(desktop_action)
            self._append_message("Jarvis", response)
            self._hero.setText("Ready")
            self._set_visual_state("ready")

    def _append_message(self, speaker: str, text: str) -> None:
        safe_speaker = html.escape(speaker)
        safe_text = html.escape(text).replace("\n", "<br>")
        color = "#68e8dc" if speaker == "Jarvis" else "#ffd27a"
        self._conversation.append(
            f"<div style='margin:10px 0'><b style='color:{color}'>{safe_speaker}</b>"
            f"<div style='margin-top:4px'>{safe_text}</div></div>"
        )

    @Slot(str, object)
    def _handle_voice_event(self, kind: str, text: object) -> None:
        message = str(text or "")
        if kind == "wake":
            self._hero.setText("Listening to you…")
            self._set_visual_state("command")
        elif kind == "transcript":
            self._last_transcript = message
            self._append_message("You", message)
            self._hero.setText("Thinking…")
            self._set_visual_state("thinking")
        elif kind == "response":
            self._append_message("Jarvis", message)
            self._hero.setText("Speaking…")
            self._set_visual_state("speaking")
            self._tray.showMessage(
                "Jarvis", message[:240], QSystemTrayIcon.MessageIcon.Information, 6000
            )
        elif kind == "reminder":
            self.show_and_raise()
            self._append_message("Jarvis", f"Reminder: {message}")
        elif kind == "error":
            self.show_and_raise()
            self._append_message("Jarvis error", message)
            self._hero.setText("Needs attention")
            self._set_visual_state("error")

    @Slot()
    def submit_typed_command(self) -> None:
        text = self._command_input.text().strip()
        if not text:
            return
        self._command_input.clear()
        self._append_message("You", text)
        self._hero.setText("Thinking…")
        self._set_visual_state("thinking")
        request = QNetworkRequest(QUrl(f"{self._base_url}/assistant/respond"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self._network.post(request, json.dumps({"text": text}).encode("utf-8"))
        reply.setProperty("jarvis_kind", "manual_response")
        reply.finished.connect(self._reply_finished)

    @Slot()
    def open_gmail(self) -> None:
        QDesktopServices.openUrl(QUrl("https://mail.google.com/mail/u/0/#inbox"))

    @Slot()
    def toggle_presence(self) -> None:
        path = "/presence/disable" if self._presence_enabled else "/presence/enable"
        self._request("presence", path, post=True)

    @Slot()
    def toggle_voice(self) -> None:
        status = self._voice_runtime.status()
        if not status.running:
            self._voice_runtime.start()
        else:
            self._voice_runtime.set_enabled(not status.enabled)
        self._refresh_native_voice()

    @Slot()
    def open_voice(self) -> None:
        QDesktopServices.openUrl(QUrl(f"{self._base_url}/wake"))

    @Slot()
    def open_api_docs(self) -> None:
        QDesktopServices.openUrl(QUrl(f"{self._base_url}/docs"))

    @Slot()
    def open_control_center(self) -> None:
        QDesktopServices.openUrl(QUrl(f"{self._base_url}/control"))

    @Slot()
    def show_and_raise(self) -> None:
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_and_raise()

    @Slot()
    def quit_application(self) -> None:
        self._really_quit = True
        self._voice_runtime.stop()
        self._camera_publisher.request_stop()
        self._stop_managed_supervisor()
        QApplication.quit()

    def _stop_managed_supervisor(self) -> None:
        if self._managed_supervisor is None or self._managed_supervisor.poll() is not None:
            return
        self._managed_supervisor.terminate()
        try:
            self._managed_supervisor.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self._managed_supervisor.kill()
            self._managed_supervisor.wait(timeout=3)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._really_quit:
            self._really_quit = True
            self._voice_runtime.stop()
            self._camera_publisher.request_stop()
            self._stop_managed_supervisor()
        event.accept()


def run() -> int:
    """Launch one native Jarvis control panel instance."""
    app = QApplication(sys.argv)
    app.setApplicationName("Local Jarvis")
    app.setQuitOnLastWindowClosed(True)
    lock_path = QDir(QDir.tempPath()).filePath("local-jarvis-desktop.lock")
    instance_lock = QLockFile(lock_path)
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(100):
        QMessageBox.information(None, "Local Jarvis", "The Jarvis control panel is already open.")
        return 0
    managed_supervisor: subprocess.Popen[bytes] | None = None
    if "--managed" in sys.argv:
        project_root = Path.cwd()
        pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
        executable = str(pythonw) if pythonw.is_file() else sys.executable
        managed_supervisor = subprocess.Popen(
            [executable, "-m", "jarvis.supervisor"],
            cwd=project_root,
            close_fds=True,
        )
    settings = get_settings()
    window = JarvisWindow(
        f"http://127.0.0.1:{settings.port}",
        settings.face_camera_index,
        managed_supervisor,
    )
    window.showMaximized()
    exit_code = app.exec()
    window._stop_managed_supervisor()
    instance_lock.unlock()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
