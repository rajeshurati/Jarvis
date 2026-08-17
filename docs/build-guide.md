# Local Jarvis build guide

This guide explains the project in the same ten phases used to build it. Each phase
starts with the concept and architecture, then identifies the implementation files,
verification, and the command used to run the resulting vertical slice.

## Folder structure

```text
local-jarvis/
|-- src/jarvis/
|   |-- api/             FastAPI boundary and localhost user interfaces
|   |-- application/     Use cases, orchestration, and workflow policy
|   |-- capabilities/    Typed contracts; no operating-system dependencies
|   |-- adapters/        Ollama, audio, vision, SQLite, email, and Windows adapters
|   |-- core/            Settings, persona, logging, and safety policy
|   |-- desktop.py       Signed-in PySide6 tray and screen/camera bridge
|   |-- native_voice.py  Always-listening full-duplex voice state machine
|   |-- supervisor.py    Crash recovery for Jarvis and Ollama
|   `-- main.py          API entry point
|-- tests/               Unit and integration acceptance tests
|-- scripts/             Windows startup, recovery, and alarm scripts
|-- models/              Local model weights; ignored by source control
|-- data/                SQLite, profiles, and generated artifacts; local only
|-- logs/                Structured runtime logs; local only
|-- docs/                Architecture and acceptance documentation
|-- .env.example         Safe configuration template
`-- pyproject.toml       Dependencies, entry points, and quality gates
```

The dependency direction is `api -> application -> capabilities`. Adapters implement
capability contracts and are assembled only in `application/factory.py`. This keeps
model and Windows details out of safety policy and makes each component replaceable.

## Phase 1: project setup

### Concept and architecture

Start with a modular monolith. A laptop does not benefit from many network services,
but it does benefit from strict internal boundaries. FastAPI is bound to loopback,
Pydantic validates configuration, and every external action has a typed interface.

### Files

- `pyproject.toml`: Python 3.12 package metadata, optional dependency groups, console
  entry points, strict Ruff/mypy settings, pytest, and the coverage gate.
- `.env.example`: documented local-first defaults; networking and room monitoring are
  off until explicitly enabled.
- `src/jarvis/core/config.py`: validates paths, ports, model locations, privacy flags,
  audio channels, biometric thresholds, and email configuration.
- `src/jarvis/core/logging.py`: structured application logging.
- `src/jarvis/core/safety.py`: action-risk classification and confirmation policy.
- `src/jarvis/api/app.py`: application lifespan, service composition, and routers.
- `src/jarvis/api/routes/health.py`: small readiness endpoint used by supervision.
- `src/jarvis/main.py`: localhost Uvicorn entry point.
- `tests/conftest.py`, `tests/test_config.py`, `tests/test_safety.py`, and
  `tests/test_api.py`: isolated settings and first API acceptance tests.

### Verify and run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[all,dev]"
.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_api.py
.\.venv\Scripts\jarvis.exe
```

Open `http://127.0.0.1:8765/health`; it must return `status: ok` and
`local_only: true`.

## Phase 2: local speech recognition

### Concept and architecture

Microphone capture and transcription are separate. The recorder creates bounded PCM
audio, while faster-whisper performs local inference. Temporary recordings are always
deleted, and browser/native uploads are accepted only on localhost.

### Files

- `capabilities/speech.py`: audio, transcription, wake-word, and synthesis contracts.
- `adapters/audio/sounddevice_recorder.py`: selected Windows input device and array
  channel capture.
- `adapters/speech/faster_whisper.py`: lazy local CTranslate2/Whisper inference.
- `application/voice_service.py`: serialization, duration bounds, and cleanup.
- `api/routes/voice.py`: device inventory, recording, transient upload, and runtime
  health endpoints.
- `tests/test_voice_service.py`: recording cleanup, validation, and transcription.

### Verify and run

```powershell
Invoke-RestMethod http://127.0.0.1:8765/voice/devices
Invoke-RestMethod -Method Post `
  "http://127.0.0.1:8765/voice/transcribe-recording?duration_seconds=5"
```

Audio is never sent outside the laptop.

## Phase 3: wake word and continuous conversation

### Concept and architecture

Wake-word inference must be cheap enough to run continuously. openWakeWord evaluates
short frames and activates Whisper only after “Hey Jarvis.” The signed-in desktop
process owns the microphone because Windows background sessions cannot reliably use
interactive audio devices. After each response, a silence-bounded follow-up window
keeps the conversation natural. Incoming speech during playback stops the current
answer and becomes the new command.

### Files

- `adapters/speech/openwakeword_detector.py`: local ONNX wake scoring.
- `application/wake_service.py`: cooldown and streaming boundaries.
- `native_voice.py`: one microphone stream, wake/command/thinking/speaking states,
  follow-up capture, barge-in, reminders, and localhost API client.
- `api/routes/wake.py`: optional browser status/fallback interface.
- `desktop.py`: starts the native runtime and publishes its current health.
- `tests/test_wake_service.py` and `tests/test_native_voice.py`: detection, follow-up,
  interruption, enrollment audio, authorization, and pause/resume tests.

### Verify and run

Start `jarvis-desktop`, close the browser, and confirm
`GET /voice/runtime-status` reports `running=true`, `enabled=true`, and
`state=listening`. Say “Hey Jarvis,” wait for “Yes?”, and speak normally. Speak over
the reply to verify immediate interruption.

## Phase 4: local language model and specialist routing

### Concept and architecture

The language model is advisory, not an authority boundary. Deterministic tools are
matched first. Questions that do not map to a tool go to loopback Ollama with bounded
history, local memory context, the Jarvis behavior contract, and one best-fit
specialist profile.

### Files

- `capabilities/language.py`: replaceable chat and vision model contracts.
- `adapters/language/ollama_client.py`: validated loopback chat requests and timeouts.
- `application/conversation_policy.py`: incomplete-question handling, topic changes,
  and short spoken answers.
- `application/agent_orchestrator.py`: deterministic executive, engineering, cloud,
  research, project, career, finance, learning, document, and security profiles.
- `application/assistant_service.py`: serialized conversation, tool-first routing,
  bounded memory, audit, and local-model fallback.
- `core/persona.py`: permanent Jarvis behavior, privacy, truth, and voice rules.
- `tests/test_assistant_service.py`, `tests/test_conversation_policy.py`, and
  `tests/test_agent_orchestrator.py`: routing and context acceptance.

### Verify and run

```powershell
$body = @{text='Actually, new topic: what is two plus two?'} | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8765/assistant/respond `
  -ContentType application/json -Body $body
```

The installed chat model is `qwen3:1.7b`; screen vision uses `qwen3.5:0.8b` so the
smaller vision model does not consume chat memory.

## Phase 5: local speech synthesis

### Concept and architecture

Piper converts only the final concise answer into a 16-bit PCM WAV. Synthesis is
serialized, temporary files are removed, and playback is chunked so barge-in can stop
it. The supervisor tolerates transient health delays during a cold model load.

### Files

- `adapters/speech/piper_synthesizer.py`: lazy local voice loading and WAV validation.
- `application/speech_service.py`: serialized rendering and guaranteed cleanup.
- `api/routes/assistant.py`: `/assistant/speak` returns local `audio/wav` bytes.
- `native_voice.py`: interruptible PortAudio playback.
- `tests/test_speech_service.py`: byte output, cleanup, and error behavior.
- `supervisor.py`: repeated-failure health policy prevents false restarts during cold
  local inference.

### Verify and run

Post `{"text":"Jarvis voice check"}` to `/assistant/speak`. The response must begin
with a RIFF/WAVE header. This test can save the WAV without playing it.

## Phase 6: desktop and workflow automation

### Concept and architecture

Natural language must never become an unrestricted shell command. Jarvis exposes
small typed operations, validates arguments and path containment, previews
consequential work, and executes only after confirmation. Workflows persist a
checkpoint after every step so they can resume safely after a restart.

### Files

- `capabilities/automation.py`, `capabilities/files.py`, and `capabilities/system.py`:
  typed action contracts and errors.
- `adapters/automation/windows_desktop.py`: fixed application aliases, installed-app
  discovery, safe public HTTPS URLs, and browser search.
- `adapters/automation/pyautogui_input.py`: bounded click, type, and key operations.
- `adapters/automation/windows_system.py`: status, Settings URIs, and reversible volume.
- `adapters/automation/developer_commands.py`: fixed, no-shell developer diagnostics.
- `adapters/files/local_search.py`, `local_manager.py`, and `document_reader.py`:
  contained search/write/copy/move/recycle and local extraction.
- `application/semantic_desktop_service.py`: OCR label lookup with ambiguity rejection.
- `application/workflow_service.py` and `planner_service.py`: durable steps, safe-plan
  validation, confirmation checkpoints, cancellation, and resume.
- `application/tool_router.py`: deterministic natural-language grammar and pending
  confirmations.
- `tests/test_windows_desktop.py`, `test_windows_system.py`, `test_file_manager.py`,
  `test_semantic_desktop_service.py`, `test_workflow_service.py`,
  `test_planner_service.py`, and `test_developer_commands.py`: safety acceptance.

### Verify and run

“Open calculator” is immediate. “Type hello,” “fill field Email,” file writes, moves,
recycling, and email sending stage a preview and require the exact confirmation phrase.
Unsupported dictated commands are rejected and never passed to a shell.

## Phase 7: vision, face, speaker, OCR, and room presence

### Concept and architecture

Raw camera and screen images are transient. The interactive tray publishes fresh
in-memory frames to the localhost API. One continuous camera session is used only
while room monitoring is enabled; disabling it closes the device and clears the
cached frame. InsightFace and speaker models store normalized embeddings rather than
recordings. Biometrics are convenience identity signals, never sole approval for a
sensitive action. YOLO runs in a disposable worker to release model memory.

### Files

- `capabilities/identity.py` and `capabilities/vision.py`: camera, biometric, OCR,
  object, and screen contracts.
- `adapters/identity/insightface_engine.py`, `face_profiles.py`, `opencv_camera.py`, and
  `camera_snapshot_store.py`: face embedding, derived profile storage, and the
  no-flicker interactive camera bridge.
- `adapters/identity/onnx_speaker_engine.py` and `voice_profiles.py`: local voiceprint
  embeddings and profiles.
- `adapters/vision/rapidocr_reader.py`: local OCR.
- `adapters/vision/snapshot_store.py`, `mss_capture.py`, and `ollama_vision.py`:
  current-screen capture and local multimodal description.
- `adapters/vision/isolated_yolo_detector.py` and `yolo_worker.py`: isolated object
  recognition.
- `application/identity_service.py`, `speaker_service.py`, `presence_service.py`,
  `object_service.py`, and `screen_service.py`: biometric and vision use cases.
- `api/routes/identity.py`, `speaker.py`, `camera.py`, `screen.py`, and `presence.py`:
  localhost control and status.
- The corresponding identity, speaker, OCR, screen, object, snapshot, and presence
  tests verify these boundaries without retaining personal media.

### Verify and run

`GET /diagnostics` must report all five model categories ready. Enrollment requires
Rajesh to be physically present and intentionally say “Enroll my face” or “Enroll my
voice.” Room monitoring remains off until enabled; while enabled, the camera light is
steady rather than cycling.

## Phase 8: local memory and productivity

### Concept and architecture

SQLite is the authoritative source because it provides reliable edit/delete,
transactions, and export without a vector database. Conversation is bounded; stable
preferences are explicit. Projects, tasks, notes, reminders, workflows, presence
events, and redacted audit records use structured tables.

### Files

- `capabilities/memory.py`: immutable records and the memory-store contract.
- `adapters/memory/sqlite_store.py`: schema migration and transactional operations.
- `api/routes/memory.py`: memory CRUD, projects, tasks, notes, and reminders.
- `api/routes/control.py`: non-technical conversation, memory, projects, reminders,
  status, and privacy controls.
- `application/productivity_service.py`: local EML, ICS, DOCX, PPTX, and XLSX creation.
- `application/document_service.py`: local extraction, OCR, and model summarization.
- `application/code_service.py`: source generation into `data/code` without execution.
- Memory, productivity, document, and code tests verify persistence and artifacts.

### Verify and run

Open `http://127.0.0.1:8765/control`. Add, edit, search, and delete a memory; create a
project task; and schedule a reminder. Restart Jarvis and verify the records remain.

## Phase 9: multi-agent coordination and connected capabilities

### Concept and architecture

“Agent” means an independently typed specialist service coordinated through a central
assistant, not an unsupervised process with arbitrary computer authority. Voice,
vision, identity, memory, planning, automation, coding, research, productivity, and
system control can be replaced independently. The central coordinator selects a
specialist persona and invokes only deterministic capability boundaries.

### Files

- `application/agent_orchestrator.py`: best-fit specialist selection.
- `application/assistant_service.py`: central coordinator.
- `application/factory.py`: dependency composition; this is the only place concrete
  adapters are wired together.
- `adapters/productivity/web_research.py`: explicit opt-in, multi-domain evidence,
  direct source retrieval, prompt-injection isolation, citations, and local synthesis.
- `adapters/productivity/tls_email.py`: bounded TLS IMAP/SMTP; sending is separately
  confirmed.
- `api/routes/workflows.py` and `audit.py`: durable coordination and observability.
- `tests/test_web_research.py`, `test_tls_email.py`, `test_tool_router.py`, and
  `test_agent_orchestrator.py`: agent/tool authority acceptance.

### Verify and run

With networking disabled, research and email must fail closed. After the owner supplies
TLS credentials or explicitly enables research, only that configured capability may
use the network; prompts, memory, audio, images, and model inference remain local.

## Phase 10: production optimization and deployment

### Concept and architecture

Production quality includes startup, crash recovery, diagnostics, privacy defaults,
bounded resources, observable failures, and a repeatable acceptance suite. The API and
Ollama are supervised background services; the PySide6 process runs in the interactive
session for audio, screen, webcam, and tray UI.

### Files

- `desktop.py`: single-instance tray, native voice, interactive media bridges, status,
  and control-center links.
- `supervisor.py`: bounded backoff, startup grace, repeated-failure health checks, and
  recovery of owned processes only.
- `scripts/start_jarvis.ps1`: local readiness startup helper.
- `scripts/install_autostart.ps1`: idempotent sign-in task installation.
- `scripts/repair_windows_audio.ps1`: explicit administrator-only device recovery.
- `api/routes/diagnostics.py`: disk, model inventory, and component readiness without
  activating sensors.
- `docs/requirements-audit.md`: requirement-to-evidence matrix.
- `docs/capability-status.md`: software acceptance versus personal prerequisites.

### Final verification

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\mypy.exe src\jarvis
.\.venv\Scripts\python.exe -m pytest --cov=jarvis --cov-report=term -q
powershell -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1
```

The final live checks are `/health`, `/diagnostics`, `/voice/runtime-status`,
`/screen/snapshot/status`, `/camera/snapshot/status`, and the Windows startup tasks.
Face/voice enrollment, email credentials, and mandatory Windows consent cannot be
fabricated by software and therefore remain explicit owner-provided prerequisites.

