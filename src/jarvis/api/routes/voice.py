"""Local voice-recognition endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from jarvis.application.voice_service import VoiceRecognitionService
from jarvis.capabilities.speech import AudioDeviceError, ModelUnavailableError, SpeechError

router = APIRouter(prefix="/voice", tags=["voice"])


class AudioDeviceResponse(BaseModel):
    """Safe microphone metadata."""

    index: int
    name: str
    input_channels: int
    default_sample_rate: float


class TranscriptResponse(BaseModel):
    """Speech recognition response."""

    text: str
    language: str
    language_probability: float
    duration_seconds: float


class NativeRuntimeStatusInput(BaseModel):
    """Status published by the signed-in desktop audio process."""

    running: bool
    enabled: bool
    state: str
    last_error: str | None = None


class NativeRuntimeStatus(NativeRuntimeStatusInput):
    """Observable background-voice readiness without exposing audio or transcripts."""

    updated_at: datetime | None = None


VOICE_TEST_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Jarvis Voice Test</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center;
           background: #0b1020; color: #edf4ff; }
    main { width: min(560px, calc(100% - 40px)); padding: 32px;
           border: 1px solid #263552; border-radius: 20px; background: #121a2c; }
    h1 { margin-top: 0; }
    button { width: 100%; padding: 16px; border: 0; border-radius: 12px;
             font-weight: 700; font-size: 17px; background: #5eead4; color: #082f2c;
             cursor: pointer; }
    button:disabled { opacity: .55; cursor: wait; }
    #status { min-height: 28px; margin: 22px 0 8px; color: #a5b4fc; }
    #result { min-height: 72px; padding: 16px; border-radius: 12px;
              background: #090e1a; white-space: pre-wrap; }
  </style>
</head>
<body>
  <main>
    <h1>Jarvis microphone test</h1>
    <p>Press the button, allow microphone access, then speak for five seconds.</p>
    <button id="record">Record and transcribe</button>
    <div id="status">Ready.</div>
    <div id="result">Your transcript will appear here.</div>
  </main>
  <script>
    const button = document.querySelector("#record");
    const statusBox = document.querySelector("#status");
    const resultBox = document.querySelector("#result");
    function encodeWav(chunks, sampleRate) {
      const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
      const buffer = new ArrayBuffer(44 + length * 2);
      const view = new DataView(buffer);
      const writeText = (offset, text) => {
        for (let index = 0; index < text.length; index += 1) {
          view.setUint8(offset + index, text.charCodeAt(index));
        }
      };
      writeText(0, "RIFF");
      view.setUint32(4, 36 + length * 2, true);
      writeText(8, "WAVE");
      writeText(12, "fmt ");
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true);
      view.setUint16(22, 1, true);
      view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * 2, true);
      view.setUint16(32, 2, true);
      view.setUint16(34, 16, true);
      writeText(36, "data");
      view.setUint32(40, length * 2, true);
      let offset = 44;
      chunks.forEach(chunk => chunk.forEach(sample => {
        const bounded = Math.max(-1, Math.min(1, sample));
        view.setInt16(offset, bounded < 0 ? bounded * 32768 : bounded * 32767, true);
        offset += 2;
      }));
      return new Blob([buffer], { type: "audio/wav" });
    }
    button.addEventListener("click", async () => {
      button.disabled = true;
      resultBox.textContent = "";
      let remaining = 5;
      statusBox.textContent = `Recording now — ${remaining} seconds remaining`;
      const timer = setInterval(() => {
        remaining -= 1;
        if (remaining > 0) {
          statusBox.textContent = `Recording now — ${remaining} seconds remaining`;
        } else {
          statusBox.textContent = "Transcribing locally…";
          clearInterval(timer);
        }
      }, 1000);
      let stream;
      let audioContext;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];
        audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = event => {
          chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
        };
        source.connect(processor);
        processor.connect(audioContext.destination);
        await new Promise(resolve => setTimeout(resolve, 5000));
        processor.disconnect();
        source.disconnect();
        statusBox.textContent = "Transcribing locally…";
        const audio = encodeWav(chunks, audioContext.sampleRate);
        const form = new FormData();
        form.append("audio", audio, "recording.wav");
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);
        const response = await fetch("/voice/transcribe-upload", {
          method: "POST",
          body: form,
          signal: controller.signal
        });
        clearTimeout(timeout);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "Request failed");
        resultBox.textContent = payload.text || "(No speech detected. Speak closer or louder.)";
        statusBox.textContent = "Finished.";
      } catch (error) {
        resultBox.textContent = error.message;
        statusBox.textContent = "Test failed.";
      } finally {
        clearInterval(timer);
        if (audioContext) await audioContext.close();
        if (stream) stream.getTracks().forEach(track => track.stop());
        button.disabled = false;
      }
    });
  </script>
</body>
</html>"""


def _service(request: Request) -> VoiceRecognitionService:
    service: VoiceRecognitionService | None = request.app.state.voice_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service is not configured",
        )
    return service


@router.put("/runtime-status", response_model=NativeRuntimeStatus)
async def publish_runtime_status(
    request: Request, payload: NativeRuntimeStatusInput
) -> NativeRuntimeStatus:
    """Publish non-sensitive runtime health from the interactive desktop session."""
    status_payload = NativeRuntimeStatus(
        **payload.model_dump(), updated_at=datetime.now(UTC)
    )
    request.app.state.native_voice_status = status_payload
    return status_payload


@router.get("/runtime-status", response_model=NativeRuntimeStatus)
async def native_runtime_status(request: Request) -> NativeRuntimeStatus:
    """Return the last interactive background-voice health signal."""
    status_payload = getattr(request.app.state, "native_voice_status", None)
    if isinstance(status_payload, NativeRuntimeStatus):
        if status_payload.updated_at is not None:
            age = (datetime.now(UTC) - status_payload.updated_at).total_seconds()
            if age <= 15:
                return status_payload
        return NativeRuntimeStatus(
            running=False,
            enabled=status_payload.enabled,
            state="stale",
            last_error="The interactive background voice process stopped reporting.",
            updated_at=status_payload.updated_at,
        )
    return NativeRuntimeStatus(
        running=False,
        enabled=False,
        state="unavailable",
        last_error="The interactive background voice process has not reported yet.",
    )


@router.get("/devices", response_model=list[AudioDeviceResponse])
async def list_devices(request: Request) -> list[AudioDeviceResponse]:
    """List available local microphones."""
    try:
        devices = await _service(request).list_input_devices()
        return [
            AudioDeviceResponse(
                index=device.index,
                name=device.name,
                input_channels=device.input_channels,
                default_sample_rate=device.default_sample_rate,
            )
            for device in devices
        ]
    except AudioDeviceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/transcribe-recording", response_model=TranscriptResponse)
async def transcribe_recording(
    request: Request,
    duration_seconds: Annotated[float, Query(gt=0, le=120)] = 5.0,
) -> TranscriptResponse:
    """Record a bounded utterance and transcribe it entirely locally."""
    try:
        transcript = await _service(request).record_and_transcribe(duration_seconds)
        return TranscriptResponse(
            text=transcript.text,
            language=transcript.language,
            language_probability=transcript.language_probability,
            duration_seconds=transcript.duration_seconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (AudioDeviceError, ModelUnavailableError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except SpeechError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/transcribe-upload", response_model=TranscriptResponse)
async def transcribe_upload(
    request: Request,
    audio: Annotated[UploadFile, File()],
) -> TranscriptResponse:
    """Transcribe audio captured by the local browser."""
    try:
        content = await audio.read(25 * 1024 * 1024 + 1)
        transcript = await _service(request).transcribe_uploaded_audio(
            content,
            Path(audio.filename or "recording.webm").suffix.lower(),
        )
        return TranscriptResponse(
            text=transcript.text,
            language=transcript.language,
            language_probability=transcript.language_probability,
            duration_seconds=transcript.duration_seconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (ModelUnavailableError, SpeechError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/transcribe-recording", response_class=HTMLResponse)
async def voice_test_page() -> HTMLResponse:
    """Provide a local one-click test page for browser users."""
    return HTMLResponse(VOICE_TEST_PAGE)
