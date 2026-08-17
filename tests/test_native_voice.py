from __future__ import annotations

import threading
import time
import wave
from io import BytesIO

import numpy as np

from jarvis.native_voice import NativeVoiceRuntime, encode_mono_wav


class FakeDetector:
    def __init__(self) -> None:
        self.detect_next = False
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1

    def process_pcm(self, _pcm: bytes) -> tuple[bool, float]:
        detected = self.detect_next
        self.detect_next = False
        return detected, 0.9 if detected else 0.0


class FakeAudio:
    def __init__(self) -> None:
        self.callback = None
        self.spoken: list[bytes] = []
        self.block_playback = False
        self.started = False

    def start(self, callback):  # type: ignore[no-untyped-def]
        self.callback = callback
        self.started = True

    def stop(self) -> None:
        self.started = False

    def play_wav(self, payload: bytes, interrupted: threading.Event) -> bool:
        self.spoken.append(payload)
        deadline = time.monotonic() + 1
        while self.block_playback and not interrupted.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)
        return interrupted.is_set()

    def send(self, level: int) -> None:
        assert self.callback is not None
        self.callback(np.full(1_280, level, dtype=np.int16))


class FakeAPI:
    def __init__(self) -> None:
        self.transcript = "open calculator"
        self.responses: list[str] = []
        self.reminders: list[str] = []
        self.claims = 0
        self.speaker_enrollments = 0
        self.authorized = True

    def health(self) -> bool:
        return True

    def transcribe(self, payload: bytes) -> str:
        with wave.open(BytesIO(payload), "rb") as audio:
            assert audio.getnchannels() == 1
            assert audio.getframerate() == 16_000
        return self.transcript

    def respond(self, text: str) -> str:
        self.responses.append(text)
        return "Opening calculator."

    def synthesize(self, text: str) -> bytes:
        return text.encode()

    def claim_due_reminders(self) -> list[str]:
        self.claims += 1
        reminders, self.reminders = self.reminders, []
        return reminders

    def enroll_speaker(self, _wav_payload: bytes) -> str:
        self.speaker_enrollments += 1
        return "Local voice recognition is enrolled for Rajesh."

    def verify_speaker(self, _wav_payload: bytes) -> str:
        return "Voice recognized as Rajesh."

    def authorized_user_present(self) -> bool:
        return self.authorized


def wait_for(predicate, timeout: float = 2) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for native voice state")


def test_encode_mono_wav_is_memory_only() -> None:
    payload = encode_mono_wav([np.array([1, -1], dtype=np.int16)], 16_000)
    with wave.open(BytesIO(payload), "rb") as audio:
        assert audio.getnframes() == 2
        assert audio.readframes(2) == b"\x01\x00\xff\xff"


def test_wake_command_response_and_follow_up() -> None:
    detector, audio, api = FakeDetector(), FakeAudio(), FakeAPI()
    runtime = NativeVoiceRuntime(detector, audio, api, reminder_interval_seconds=60)
    runtime.start()
    detector.detect_next = True
    audio.send(0)
    wait_for(lambda: runtime.status().state == "command")

    for _ in range(10):
        audio.send(3_000)
    for _ in range(9):
        audio.send(0)

    wait_for(lambda: api.responses == ["open calculator"])
    wait_for(lambda: runtime.status().state == "command")
    assert audio.spoken == [b"Yes?", b"Opening calculator."]
    assert runtime.status().last_transcript == "open calculator"
    runtime.stop()


def test_speech_can_be_interrupted_into_a_new_command() -> None:
    detector, audio, api = FakeDetector(), FakeAudio(), FakeAPI()
    audio.block_playback = True
    runtime = NativeVoiceRuntime(detector, audio, api, reminder_interval_seconds=60)
    runtime.start()
    detector.detect_next = True
    audio.send(0)
    wait_for(lambda: runtime.status().state == "speaking")
    time.sleep(0.42)
    audio.send(4_000)
    audio.send(4_000)
    wait_for(lambda: runtime.status().state == "command")
    for _ in range(10):
        audio.send(4_000)
    for _ in range(9):
        audio.send(0)
    wait_for(lambda: bool(api.responses))
    assert api.responses == ["Actually, open calculator"]
    runtime.stop()


def test_due_reminder_is_spoken_without_browser() -> None:
    detector, audio, api = FakeDetector(), FakeAudio(), FakeAPI()
    api.reminders = ["stand up"]
    runtime = NativeVoiceRuntime(
        detector, audio, api, reminder_interval_seconds=0.01
    )
    runtime.start()
    wait_for(lambda: b"Reminder: stand up" in audio.spoken)
    assert runtime.status().state == "listening"
    runtime.stop()


def test_voice_enrollment_uses_interactive_command_audio() -> None:
    detector, audio, api = FakeDetector(), FakeAudio(), FakeAPI()
    api.transcript = "enroll my voice"
    runtime = NativeVoiceRuntime(detector, audio, api, reminder_interval_seconds=60)
    runtime.start()
    detector.detect_next = True
    audio.send(0)
    wait_for(lambda: runtime.status().state == "command")
    for _ in range(10):
        audio.send(3_000)
    for _ in range(9):
        audio.send(0)
    wait_for(lambda: api.speaker_enrollments == 1)
    assert api.responses == []
    runtime.stop()


def test_unrecognized_person_cannot_issue_native_commands() -> None:
    detector, audio, api = FakeDetector(), FakeAudio(), FakeAPI()
    api.authorized = False
    runtime = NativeVoiceRuntime(detector, audio, api, reminder_interval_seconds=60)
    runtime.start()
    detector.detect_next = True
    audio.send(0)
    wait_for(lambda: runtime.status().state == "command")
    for _ in range(10):
        audio.send(3_000)
    for _ in range(9):
        audio.send(0)
    wait_for(lambda: b"cannot verify an authorized user" in b" ".join(audio.spoken))
    assert api.responses == []
    runtime.stop()


def test_pause_ignores_audio_and_can_resume() -> None:
    detector, audio, api = FakeDetector(), FakeAudio(), FakeAPI()
    runtime = NativeVoiceRuntime(detector, audio, api, reminder_interval_seconds=60)
    runtime.start()
    runtime.set_enabled(False)
    detector.detect_next = True
    audio.send(4_000)
    time.sleep(0.03)
    assert runtime.status().state == "paused"
    runtime.set_enabled(True)
    assert runtime.status().state == "listening"
    runtime.stop()
