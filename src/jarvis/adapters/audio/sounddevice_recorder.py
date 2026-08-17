"""Microphone recording through PortAudio and sounddevice."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from jarvis.capabilities.speech import AudioDevice, AudioDeviceError


class SoundDeviceRecorder:
    """Capture PCM microphone input and encode it as a mono/stereo WAV file."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        device: int | str | None = None,
        channel_index: int = 0,
    ) -> None:
        if channel_index >= channels:
            raise ValueError("channel_index must be less than channels")
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device
        self._channel_index = channel_index

    @staticmethod
    def _libraries() -> tuple[Any, Any]:
        try:
            import numpy
            import sounddevice
        except ImportError as error:
            raise AudioDeviceError(
                'Voice dependencies are missing. Install with: pip install -e ".[voice]"'
            ) from error
        return numpy, sounddevice

    def list_input_devices(self) -> list[AudioDevice]:
        """Return devices that expose at least one input channel."""
        _, sounddevice = self._libraries()
        try:
            devices = sounddevice.query_devices()
            return [
                AudioDevice(
                    index=index,
                    name=str(device["name"]),
                    input_channels=int(device["max_input_channels"]),
                    default_sample_rate=float(device["default_samplerate"]),
                )
                for index, device in enumerate(devices)
                if int(device["max_input_channels"]) > 0
            ]
        except Exception as error:
            raise AudioDeviceError("Unable to enumerate microphone devices") from error

    def record_wav(self, destination: Path, duration_seconds: float) -> Path:
        """Record blocking PCM audio and atomically finish the WAV header."""
        numpy, sounddevice = self._libraries()
        frame_count = round(duration_seconds * self._sample_rate)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            samples = sounddevice.rec(
                frame_count,
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="int16",
                device=self._device,
            )
            sounddevice.wait()
            selected_samples = numpy.asarray(samples, dtype=numpy.int16)[
                :,
                self._channel_index : self._channel_index + 1,
            ]
            pcm_bytes = selected_samples.tobytes()
            with wave.open(str(destination), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(pcm_bytes)
        except Exception as error:
            destination.unlink(missing_ok=True)
            raise AudioDeviceError("Unable to record from the selected microphone") from error
        return destination
