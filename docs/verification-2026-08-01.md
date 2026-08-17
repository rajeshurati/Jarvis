# Production verification — 2026-08-01

This record captures direct acceptance evidence for Local Jarvis 0.18.0. It separates
software completion from private owner-provided enrollment and credentials.

## Automated gates

- Ruff: all checks passed for `src` and `tests`.
- Strict mypy: no issues in 100 source files.
- Pytest: 198 tests passed.
- Branch-aware coverage: 85.46%; required gate: 85%.
- Focused regression suites passed for the camera bridge, room presence, startup
  supervisor, structured logging, wake UI, control center, speech, and API routes.

## Installed runtime

- `/health`: `status=ok`, `version=0.18.0`, `local_only=true`.
- `/voice/runtime-status`: native desktop runtime reported `running=true`,
  `enabled=true`, `state=listening`, and no error.
- `/screen/snapshot/status`: a fresh interactive screen snapshot was available.
- `/presence/status`: monitoring disabled by default.
- `/camera/snapshot/status`: no frame available while monitoring was disabled.
- Windows tasks `Local Jarvis Supervisor` and `Local Jarvis Desktop` remained in the
  Running state after delayed rechecks.
- The supervisor action uses `pythonw.exe`; killing only the verified Jarvis API
  listener caused automatic recovery to version 0.18.0.
- Startup removed every crash-left file from the three fixed transient-media
  directories.

## Model and media evidence

- Diagnostics reported Whisper, openWakeWord, Piper, InsightFace, speaker, and YOLO
  models ready; `qwen3:1.7b` and `qwen3.5:0.8b` were installed and active.
- faster-whisper transcribed a 5.41-second local WAV as: “Good morning, Rajish. It is
  8 AM Pacific time. Jarvis is ready. Please wake up.” No cloud endpoint was used.
- A cold Piper request returned an 86,060-byte RIFF/WAVE payload in 4.6 seconds and
  left the API healthy. A warm short reply rendered in about 0.8 seconds.
- The local chat model answered a cold question in about 9 seconds and the next warm,
  topic-changing turn in about 0.4 seconds.
- Screen understanding returned a description from the current interactive snapshot.
- RapidOCR extracted 1,454 characters from a real screenshot.
- InsightFace loaded all local recognition/detection models and completed inference on
  a real image without persisting it.
- The speaker model produced a normalized 256-dimensional local embedding.
- The isolated YOLO subprocess loaded the local model, completed inference, returned
  structured results, and exited without activating the webcam.

## Capability evidence

- Safe developer command: `show Python version` returned `developer_command` and
  passed without a shell.
- Code generation created a Python source file and local AST validation passed.
- Document generation created a valid editable DOCX archive.
- Local memory was created, searched, and deleted; the final search returned no row.
- Local planning created a seven-step durable workflow after safe-command validation.
- The control center rendered live voice, identity, privacy, and explicit
  `Off · camera off` state with a monitoring toggle.
- The wake page detected the native listener, disabled its duplicate browser-microphone
  button, and displayed `Background listening active`.
- A control-center conversation returned the deterministic identity response:
  “My name is Jarvis. Say Hey Jarvis whenever you need me.”

## Camera privacy regression

The original light cycling came from opening and releasing a second webcam session for
each presence sample. The desktop now owns one continuous session only while presence
monitoring is enabled. The API consumes the fresh interactive snapshot before attempting
direct capture. Disabling monitoring closes the camera and immediately clears its
transient in-memory frame. Live status after the change was camera off/unavailable.

## Owner-provided prerequisites

The following software paths are implemented and tested but intentionally inactive:

1. Face authorization has no profile until Rajesh is physically visible and explicitly
   enrolls.
2. Speaker recognition has no profile until Rajesh explicitly supplies a live voice
   sample.
3. Email remains disabled until Rajesh enters TLS host/account details and an app
   password and opts into network access.
4. Windows may display mandatory device/UAC consent that software cannot bypass.

These are not substituted with fake credentials, stored raw biometrics, or weakened
authorization.
