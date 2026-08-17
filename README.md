# Local Jarvis 0.18

A privacy-first, voice-controlled AI assistant that runs locally and treats
computer access as a capability that must be explicitly granted.

Version 0.18 implements the complete local product scope: speech recognition,
wake-word listening, low-latency local reasoning, Piper speech, full-duplex
interruption, controlled desktop and system tools, screen understanding, OCR,
face and speaker recognition, isolated YOLO object detection, searchable SQLite
memory, project planning, resumable workflows, cited opt-in research, native Office
artifacts, a PySide6 tray application, diagnostics, startup, and crash recovery.
All AI inference is local by default.

## Phase 1 architecture

The project uses a modular monolith. Each capability will live behind a small
interface, while one process coordinates them. This is easier to debug and
package on a laptop than microservices, but keeps the boundaries needed to
replace Whisper, Ollama, Piper, or other components later.

```text
Voice / Local browser control surface
                |
          FastAPI boundary
                |
        Application services
                |
    Capability + safety interfaces
                |
 Local adapters (Ollama, audio, screen, OS, SQLite)
```

The dependency direction is inward: adapters may depend on application
contracts, but core policy never depends on a model, operating system, or UI.
High-impact actions will pass through the policy layer before execution.

## Safety model

Actions are classified as:

- `safe`: read-only or easily reversible local actions.
- `confirm`: messages, writes, automation, settings, and other consequential actions.
- `forbidden`: actions the assistant must not perform.

The default configuration binds the API to localhost, disables network access,
and requires confirmation. The audit log, allowlists, biometric session state,
and preview/confirm/execute flow are implemented at the deterministic tool boundary.

## Setup on Windows

1. Install 64-bit Python 3.12 from python.org and enable “Add Python to PATH”.
2. Open PowerShell in this folder.
3. Create and activate an isolated environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -e ".[dev,voice,vision]"
   ```

   These commands do not require PowerShell script execution. Activation is
   optional; every command below can be run directly from `.venv\Scripts`.

4. Copy `.env.example` to `.env` if you want to change defaults.
5. Run quality checks:

   ```powershell
   .\.venv\Scripts\ruff.exe check .
   .\.venv\Scripts\mypy.exe src
   .\.venv\Scripts\pytest.exe --cov
   ```

6. Start the local API:

   ```powershell
   .\.venv\Scripts\jarvis.exe
   ```

7. Visit `http://127.0.0.1:8765/health`.

The service exposes controlled capabilities through natural-language commands;
it does not expose an unrestricted shell or arbitrary remote-control endpoint.

## Phase 2: test local voice recognition

Speech recognition has two separate parts:

1. `SoundDeviceRecorder` captures 16-bit PCM microphone samples into a temporary
   WAV file.
2. `FasterWhisperTranscriber` loads a local CTranslate2 Whisper model, filters
   silence with VAD, and returns a normalized transcript.

The application service serializes microphone operations and always deletes the
temporary recording, including after failures.

### 1. Allow microphone access

In Windows, open **Settings → Privacy & security → Microphone**. Enable
microphone access and “Let desktop apps access your microphone.”

### 2. Download a model once

This is the only Phase 2 step requiring internet access. It downloads model
weights, not your audio:

```powershell
.\.venv\Scripts\hf.exe download Systran/faster-whisper-base.en `
  --local-dir models/whisper `
  --max-workers 1
```

For a lower-memory CPU test, replace `base.en` with `tiny.en`. After this
download, transcription is local and `JARVIS_ALLOW_NETWORK=false` remains the
correct setting.

If Windows reports `WinError 10054` after `model.bin` has downloaded, resume
only the small metadata files with accelerated transfer disabled:

```powershell
$env:HF_HUB_DISABLE_XET = "1"
.\.venv\Scripts\hf.exe download Systran/faster-whisper-tiny.en `
  config.json tokenizer.json vocabulary.txt `
  --local-dir models/whisper `
  --max-workers 1
```

### 3. Start and test the service

```powershell
.\.venv\Scripts\jarvis.exe
```

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/voice/devices
Invoke-RestMethod -Method Post `
  "http://127.0.0.1:8765/voice/transcribe-recording?duration_seconds=5"
```

Speak during the five-second recording. A successful response resembles:

```json
{
  "text": "Hello Jarvis",
  "language": "en",
  "language_probability": 0.99,
  "duration_seconds": 5.0
}
```

Common failures:

- `503 Voice service is not configured`: the model directory is missing.
- `503 Voice dependencies are missing`: install the `voice` dependency group.
- `503 Unable to record`: check Windows permission and the default input device.

If the Windows default input fails, select an index returned by
`/voice/devices` in `.env`. For example:

```dotenv
JARVIS_AUDIO_DEVICE_INDEX=21
JARVIS_AUDIO_SAMPLE_RATE=16000
JARVIS_AUDIO_CHANNELS=4
JARVIS_AUDIO_CHANNEL_INDEX=1
JARVIS_WHISPER_COMPUTE_TYPE=int8
```

## Phase 3: always-listening wake word

Phase 3 uses the pretrained openWakeWord `hey_jarvis` ONNX model. The signed-in
PySide6 desktop process owns one continuous 16 kHz microphone stream, evaluates
wake frames locally, and sends only the completed transient command WAV to the
localhost Whisper service. The browser page is an optional status and fallback
surface; the native listener continues when the browser is closed.

Start Jarvis, then open:

```text
http://127.0.0.1:8765/wake
```

Jarvis starts listening automatically from the desktop tray. Say "Hey Jarvis,"
then speak a command after the acknowledgement. The transcript and response appear
on the page when it is open. Use the tray dashboard to pause background listening.

The wake-word model is intentionally much smaller than Whisper and is evaluated
continuously. Whisper runs only after wake detection, reducing CPU use and
preventing ordinary room audio from being transcribed.

## Configuration

### Connect Gmail with OAuth

Jarvis uses Google's revocable OAuth flow instead of a Gmail password. In Google
Cloud, enable the Gmail API, configure an External OAuth consent screen with your
Gmail address as a test user, and create a Desktop app OAuth client. Save the
downloaded JSON as `data/google-oauth-client.json`, then run:

```powershell
.\.venv\Scripts\jarvis-google-auth.exe
```

Approve the read-only inbox and send-message permissions in the browser. Jarvis
stores the resulting token locally at `data/google-oauth-token.json`; both files
are excluded from Git. Email sending still requires an explicit spoken confirmation.

Settings use environment variables prefixed with `JARVIS_`. Secrets must not
be committed. Runtime data, logs, and model files are ignored by Git.

| Setting | Default | Meaning |
|---|---:|---|
| `JARVIS_HOST` | `127.0.0.1` | Local-only API binding |
| `JARVIS_PORT` | `8765` | API port |
| `JARVIS_LOG_LEVEL` | `INFO` | Logging threshold |
| `JARVIS_REQUIRE_CONFIRMATION` | `true` | Gate consequential actions |
| `JARVIS_ALLOW_NETWORK` | `false` | Deny cloud/network adapters by default |
| `JARVIS_AUDIO_DEVICE_INDEX` | unset | Optional microphone index from `/voice/devices` |
| `JARVIS_AUDIO_DEVICE_NAME` | unset | Stable microphone name preferred over index |
| `JARVIS_AUDIO_CHANNEL_INDEX` | `0` | Zero-based array channel saved as mono |
| `JARVIS_WAKE_MODEL_DIR` | `models/wakeword` | Local openWakeWord ONNX files |
| `JARVIS_WAKE_THRESHOLD` | `0.5` | Detection sensitivity from 0 to 1 |
| `JARVIS_WAKE_COOLDOWN_SECONDS` | `2` | Minimum delay between detections |
| `JARVIS_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama API only |
| `JARVIS_OLLAMA_MODEL` | `qwen3:1.7b` | Balanced local conversation, planning, and coding model |
| `JARVIS_OLLAMA_VISION_MODEL` | `qwen3.5:0.8b` | Separate local screen-vision model |
| `JARVIS_PIPER_MODEL` | `models/piper/en_US-lessac-medium.onnx` | Local voice model |
| `JARVIS_FACE_MODEL_ROOT` | `models/insightface` | Local InsightFace ONNX models |
| `JARVIS_FACE_SIMILARITY_THRESHOLD` | `0.45` | Minimum cosine match score |
| `JARVIS_FACE_SESSION_MINUTES` | `5` | Face authorization cache duration |

## Local operating-system capabilities

The assistant uses a typed tool router before the language model. Supported
voice requests include:

- "What can you see on my screen?" captures the current desktop in memory and
  sends it only to the loopback Ollama vision model. The screenshot is not saved.
- "What browser tabs are open?" reports tabs visible in the current screenshot
  and distinguishes tabs that are not visibly rendered.
- Speak while Jarvis is answering to stop playback immediately. Your interruption
  becomes the next command. Follow-up questions do not need the wake word.
- "Enroll my face" captures one current webcam frame, stores only a normalized
  InsightFace embedding, and starts a five-minute local authorization session.
- "Is anyone in the room?" counts current faces without saving the webcam frame.
- "What objects can you see?" uses local YOLO weights when installed; if weights
  are missing, Jarvis reports that honestly instead of pretending to see objects.
- "Recognize me" performs a new local comparison. Raw webcam images are never saved.
- "Delete face profile Rajesh" requires the spoken confirmation Jarvis provides.
- "Remember that my editor is VS Code" stores an editable preference in
  `data/jarvis.db`.
- "What do you remember?" lists saved memories with their identifiers.
- "Forget memory 1" requires the follow-up phrase "Confirm forget memory 1."
- "Create project Jarvis with objective Ship my local assistant."
- "Add task Write tests to project Jarvis."
- "Show projects."
- "Set a timer for five minutes" and "Remind me in two hours to call Mom"
  persist locally, survive restarts, and are spoken from the always-listening page.
- "Find file quarterly report" searches names in Desktop, Documents, and Downloads.
- "Summarize document quarterly report" extracts TXT, Markdown, code, PDF, or Word
  locally and summarizes it with Ollama. "Read text from image receipt" uses RapidOCR.
- "Click at 400, 250", "type hello", and "press enter" stage one bounded desktop
  input action and require "confirm desktop action" before execution.
- "Click button Record and transcribe" re-scans the current screen with local OCR,
  rejects ambiguous labels, and clicks only after desktop confirmation. "Fill field
  Email with name@example.com" uses the same fresh-screen safety boundary.
- "Draft email to person@example.com with subject Status saying Work is complete"
  saves a local `.eml` file. Calendar events use `.ics`; professional documents,
  presentations, and spreadsheets use editable `.docx`, `.pptx`, and `.xlsx` files.
- Configured TLS email can read bounded message headers. Sending always pauses for
  "confirm email action"; email and all network access are disabled by default.
- "Create workflow Morning with steps open Gmail then tell me the time" saves an
  ordered local workflow. "Run workflow 1" checkpoints every step, pauses for
  confirmation, resumes after approval, and survives service restarts.
- "Make a plan to prepare for work" uses the local planner and accepts only steps
  in the safe command registry. Unsupported, physical, or high-impact model output
  is rejected before persistence.
- "Research local AI" creates a cited local report when network access is explicitly
  enabled. Search evidence is synthesized by the local model.
- "System status", "open sound settings", and "volume up" provide bounded Windows
  status and reversible system controls.
- "Brief me", project milestones, dependencies, risks, deadlines, and task status
  are stored as structured SQLite data.
- File and folder creation, copying, moving, and recoverable Recycle Bin operations
  are restricted to Desktop, Documents, and Downloads and require confirmation.
- `GET /audit` exposes an immutable, redacted local action trail.
- `GET /diagnostics` reports installed/active models and component readiness without
  opening the microphone, webcam, or screen.
- "Open calculator," "open Notepad," "open Gmail," time, and date remain allowlisted.

Memory can also be managed from the localhost API: `GET /memory`, `PUT /memory`,
`DELETE /memory/{id}`, `GET /projects`, and the project task endpoints shown in
the interactive API at `http://127.0.0.1:8765/docs`.

## Completed stack

1. Setup: Python 3.12, FastAPI, Pydantic Settings, pytest, Ruff, mypy.
2. Speech-to-text: faster-whisper with built-in Silero VAD. **Complete.**
3. Wake word: openWakeWord, with a push-to-talk fallback. **Complete.**
4. Local LLM: Ollama with Qwen 3 1.7B for chat and Qwen 3.5 0.8B for vision. **Complete.**
5. Speech: Piper neural TTS. **Complete.**
6. Automation: typed native actions, safe file management, semantic OCR clicks,
   form filling, system controls, and durable workflows. **Complete.**
7. Vision: screen capture, local multimodal understanding, face enrollment, and
   short-lived face authorization, speaker recognition, presence, and isolated YOLO
   object detection. **Complete.**
8. Memory: authoritative SQLite preferences, conversation, projects, tasks, reminders,
   timers, structured risks/dependencies/milestones, search, and editable APIs. **Complete.**
9. Orchestration: specialist selection, validated local planning, durable checkpoints,
   approval interrupts, cancellation, audit, and recovery. **Complete.**
10. Production: native always-on tray voice, non-technical control center, startup tasks, diagnostics/model inventory, split-model
    memory optimization, isolated heavy vision, logging, tests, and supervision. **Complete.**

Install sign-in startup with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1
```

The build can be complete while account- or person-specific configuration remains
inactive. Email needs user-owned TLS credentials; face and speaker profiles require
Rajesh to enroll live at the webcam/microphone. These are privacy prerequisites, not
missing implementations.

See `docs/build-guide.md` for the complete ten-phase implementation walkthrough,
`docs/requirements-audit.md` for requirement-by-requirement acceptance evidence,
and `docs/architecture.md` for the design decisions and phase boundaries.
