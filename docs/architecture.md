# Architecture

## Design goals

Local Jarvis is local-first, least-privilege, observable, testable, and
replaceable. “Local-first” means no personal content leaves the laptop unless
the user enables a specific network capability for a specific purpose.

## Why a modular monolith

Audio, vision, language, memory, and automation have different dependencies,
but they do not need separate network services on one laptop. A modular
monolith avoids distributed-system overhead while preserving clear interfaces.
Heavy model inference may later run in supervised worker processes so crashes
or GPU memory pressure do not take down the coordinator.

## Packages

- `api`: localhost HTTP boundary and native/browser UI integration.
- `application`: use cases and orchestration.
- `core`: configuration, logging, safety policy, shared domain types.
- `capabilities`: stable interfaces for voice, vision, memory, and tools.
- `adapters`: concrete local implementations and OS integrations.

All packages are implemented behind typed boundaries; platform and model adapters
remain replaceable.

## Request lifecycle

Requests follow:

1. Authenticate the active user.
2. Capture and transcribe an utterance.
3. Plan a typed action using the local model.
4. Validate tool arguments and evaluate policy.
5. Preview and obtain confirmation when required.
6. Execute through a narrowly scoped adapter.
7. Record an audit event and produce a spoken response.

The language model never receives unrestricted shell or desktop access. It
selects from typed tools, and deterministic code enforces policy.

## Threat model

Primary risks include accidental commands, prompt injection in documents or
web pages, impersonation, malicious files, secrets in logs, and over-broad OS
permissions. Face or voice recognition is a convenience signal, not sufficient
authorization for destructive or financial actions. Sensitive actions require
an explicit confirmation channel and may require OS authentication.

## Technology decisions

- **Ollama** provides the simplest local model lifecycle and tool calling.
  vLLM is better for a dedicated GPU server, not the default laptop path.
- **faster-whisper** offers efficient local transcription through CTranslate2.
- **Piper/Kokoro** are adapter choices, not core dependencies.
- **SQLite** is the source of truth. Vector retrieval is optional and derived;
  this makes memory export, editing, and deletion reliable.
- A small native workflow coordinator is used instead of LangGraph because the
  required checkpoints, interruption, confirmation, and restart recovery are bounded
  and do not justify another runtime dependency on this laptop.
- **PySide6** is preferred over Electron for a Python-first, lower-overhead
  desktop application.

## Verification boundary

Each phase must end with automated tests and a runnable vertical slice. Later
phases must not bypass the safety policy or silently enable networking.
