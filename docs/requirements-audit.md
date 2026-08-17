# Requirements acceptance audit

This is the authoritative mapping from the original Jarvis request to implementation
evidence. `Implemented` means a production code path exists and is covered by unit or
integration tests. `Personal setup` means the code is complete but the private sample
or credential can only come from Rajesh.

| Original requirement | Acceptance | Evidence |
|---|---|---|
| Always listen for “Jarvis” | Implemented, live | `native_voice.NativeVoiceRuntime` runs inside the signed-in tray session; `/voice/runtime-status` reported `running=true`, `enabled=true`, `state=listening`. |
| Local speech-to-text | Implemented, live | faster-whisper uses the installed local model; transient interactive WAV upload never leaves localhost. |
| Local natural-language understanding | Implemented, live | Ollama is loopback-only with Qwen chat and separate vision models. |
| Natural spoken reply | Implemented, live | Piper returned valid local RIFF/WAVE bytes; cold and warm synthesis survived health supervision, and native PortAudio output is interruptible. |
| Conversational follow-up | Implemented | After every reply the runtime opens a silence-bounded follow-up window without requiring the wake word. |
| Interrupt Jarvis while speaking | Implemented | Full-duplex input monitors speech during output, stops the turn, preserves pre-roll, and changes to the new command. |
| Open applications | Implemented | Core apps plus safely discovered VS Code, Terminal, Office, browsers, Teams, and Spotify use fixed executable aliases and no dictated shell. |
| Search files | Implemented | Bounded search spans Desktop, Documents, and Downloads. |
| Read/send email with permission | Implemented; personal setup | TLS IMAP/SMTP code exists; credentials and network opt-in are required; sends require confirmation. |
| Open websites/search web | Implemented | Named sites, public HTTPS validation, and explicit browser search are supported. |
| Manage folders/files | Implemented | Scoped create/copy/move/recycle with path containment and confirmations. |
| Control appropriate settings | Implemented | Status, Settings pages, and reversible volume controls are bounded. |
| Reminders/timers | Implemented, live | SQLite reminders are atomically claimed and spoken by the native background runtime without a browser. |
| Answer questions | Implemented, live | Local model with concise conversation policy and topic-change handling. |
| Summarize documents | Implemented | TXT/Markdown/code/PDF/DOCX extraction plus long-form local synthesis. |
| Generate code | Implemented, live | Fifteen language targets save new local source artifacts; a live Python artifact passed AST validation, and generated code is never automatically executed. |
| Webcam face recognition | Implemented; personal setup | InsightFace embeddings and profile store are local; raw enrollment photos are never persisted. |
| Authorized users only | Implemented after enrollment | Native voice checks the current camera frame before every non-enrollment command once a face profile exists. |
| Enter/leave detection | Implemented, live | Presence monitoring persists transitions only, uses one continuous interactive camera session, and clears the transient frame immediately when disabled. |
| OCR images/screen | Implemented | RapidOCR reads local images and fresh screen snapshots. |
| Webcam object recognition | Implemented | YOLO runs in a disposable subprocess so memory is reclaimed after inference. |
| Screen understanding | Implemented, live | The interactive tray publishes memory-only screenshots to the local vision model. |
| Mouse/keyboard control | Implemented | PyAutoGUI actions are typed and confirmation-gated. |
| Fill forms/click buttons | Implemented | OCR locates visible labels; ambiguous targets fail closed; execution needs confirmation. |
| Repetitive desktop workflows | Implemented | Durable SQLite workflows support safe steps, checkpoints, resume, cancellation, and audit. |
| Preferences and conversation memory | Implemented | SQLite stores explicit memories and bounded conversation locally. |
| Edit/delete memory | Implemented | REST APIs and `/control` provide non-technical editing/deletion. |
| Ongoing project memory | Implemented | Objectives, tasks, status, deadlines, milestones, risks, dependencies, and briefings are structured. |
| Local/private by default | Implemented | Loopback validation, local models, transient audio/images, local SQLite, and opt-in networking. |
| FastAPI backend | Implemented, live | Modular routers and lifespan services run under Uvicorn. |
| PySide6 desktop UI | Implemented, live | Tray dashboard owns interactive screen, webcam, microphone, speaker, and control links. |
| Modular OOP architecture | Implemented | Capability protocols, application services, adapters, API routes, and composition root are separated. |
| Independent agents/orchestration | Implemented | Voice, vision, identity, memory, planning, automation, coding, research, productivity, and system services are independently typed; the assistant and workflow coordinator route them centrally. |
| Executive and specialist roles | Implemented | Executive, software, AI, cloud/DevOps, research, project, career, email, calendar, documents, automation, finance, learning, and security profiles are selected deterministically. |
| Deep cited research | Implemented; opt-in | Search results are diversified by domain, source pages are fetched directly, active content is ignored, and the local model compares evidence with citations. |
| Professional documents | Implemented | Real editable DOCX, PPTX, XLSX, EML, and ICS artifacts can be created from supplied content or a local-model brief. |
| Logging/error handling | Implemented | Rotating structured local logs, typed domain errors, API mappings, startup cleanup, timeouts, and retry/backoff are present. |
| Tests and production checks | Implemented | 198 tests passed with 85.46% branch-aware coverage; Ruff and strict mypy passed across 100 source files, followed by live readiness checks. |
| Startup and recovery | Implemented, installed | Windowless Windows sign-in tasks start the supervisor and interactive desktop; a verified API termination recovered automatically with bounded backoff and transient-failure tolerance. |

## External prerequisites that software cannot fabricate

1. Rajesh must be physically visible for face enrollment.
2. Rajesh must speak for voiceprint enrollment.
3. Email credentials/app password must be entered by the account owner.
4. Windows may require a one-time microphone/camera/UAC prompt; Jarvis cannot bypass OS consent.

Those do not reduce software acceptance coverage, but the associated personalized
features remain inactive until their prerequisites are supplied.

The dated direct runtime evidence is recorded in `docs/verification-2026-08-01.md`.
