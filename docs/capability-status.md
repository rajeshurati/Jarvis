# Capability status

Version 0.18.0 has a production code path for every capability in the approved
local Jarvis scope. “100%” here means the software acceptance matrix is complete
and verified; it does not mean zero physical latency, possession of user-owned
email credentials, or biometric enrollment without the user being present.

| Area | Weight | Earned | Verified evidence |
|---|---:|---:|---|
| Native voice conversation | 16 | 16 | The signed-in tray process owns the microphone, continuously runs local Hey Jarvis, uploads only transient WAV to localhost, supports follow-ups and barge-in, and publishes live health. The browser can be closed. |
| Local reasoning and code | 10 | 10 | Qwen 3 1.7B chat and Qwen 3.5 0.8B vision models, bounded context, specialist routing, safe planning, code-file generation, and non-executing Python/JSON syntax validation are implemented. |
| Computer control | 14 | 14 | Installed-app discovery, allowlisted apps/sites, validated public HTTPS URLs, web search, screen-aware clicks/forms, typed mouse/keyboard actions, scoped file management, settings, volume, and durable workflows are available. |
| Vision and identity | 12 | 12 | Transient screen/camera bridges, multimodal screen understanding, OCR, InsightFace, authorized-user enforcement after enrollment, room transitions, uploaded interactive speaker samples, and isolated YOLO are implemented. |
| Memory and organization | 10 | 10 | Editable/searchable preferences, conversation, projects, tasks, milestones, dependencies, risks, reminders, timers, briefings, and audit data persist in SQLite. |
| Proactive and agent operation | 12 | 12 | Independent capability services, specialist profiles, safe local planning, checkpoints, confirmations, cancellation, native reminder speech, transition monitoring, and crash recovery are centrally coordinated. |
| Email, calendar, research, documents | 14 | 14 | Local EML drafts, opt-in TLS mail, ICS events, direct multi-source page evidence with citations, document summarization/OCR, and locally generated DOCX/PPTX/XLSX artifacts are implemented. |
| Desktop product and deployment | 8 | 8 | PySide6 tray, background audio, no-flicker camera/screen bridges, non-technical control center, diagnostics, windowless sign-in startup, rotating logs, and supervisor recovery are installed. |
| Privacy, safety, verification | 4 | 4 | Loopback binding, local inference, explicit network gating, typed capabilities, confirmation for consequential actions, transient biometric media, redacted audit, strict lint/types, and automated tests are enforced. |
| **Software acceptance total** | **100** | **100** | **Every approved software requirement has implementation and test evidence.** |

## Live readiness versus software completion

The installed runtime is live for wake word, microphone, speech recognition,
local chat, speech output, desktop UI, screen capture, webcam bridge, OCR, object
detection, memory, reminders, files, apps, documents, and startup recovery. Room
monitoring is privacy-off after every service restart until explicitly enabled.

Three personal connections remain intentionally user-owned:

- Face profile: say “Hey Jarvis, enroll my face” while Rajesh is in front of the camera.
- Voice profile: say “Hey Jarvis, enroll my voice.” The native runtime now uses the
  same interactive microphone audio instead of asking the background API to record.
- Email account: TLS host, username, address, and an app password must be supplied by
  the account owner. Sending still requires a separate spoken confirmation.

Web research is disabled unless `JARVIS_ALLOW_NETWORK=true`; even when enabled, it
runs only after an explicit research command and the synthesis model remains local.

## Deliberate non-goals

Jarvis does not expose an unrestricted shell, bypass UAC or application permission
dialogs, authorize sensitive actions solely from biometrics, or silently delete,
send, purchase, or change important settings. “No latency” is physically impossible;
the production target is low bounded latency with the small local model kept warm.

The requirement-by-requirement evidence is in `docs/requirements-audit.md`.
The final direct acceptance run is in `docs/verification-2026-08-01.md`.
