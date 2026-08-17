"""Typed contracts for local productivity artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class ProductivityError(RuntimeError):
    """Raised when a requested productivity artifact is invalid or cannot be saved."""


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    """One locally generated, user-owned artifact."""

    kind: str
    path: Path


@dataclass(frozen=True, slots=True)
class EmailSummary:
    """Bounded email metadata returned from a configured mailbox."""

    sender: str
    subject: str
    received: str
    message_id: str | None = None


class EmailGateway(Protocol):
    """Explicitly enabled TLS email account integration."""

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Transmit one validated email."""

    def latest(self, limit: int) -> list[EmailSummary]:
        """Read bounded headers from the newest mailbox messages."""

class ProductivityTools(Protocol):
    """Generate common work artifacts without sending data externally."""

    def create_email_draft(self, recipient: str, subject: str, body: str) -> ArtifactResult:
        """Save a standards-compliant local EML draft."""

    def create_calendar_event(
        self, title: str, starts_at: datetime, duration_minutes: int
    ) -> ArtifactResult:
        """Save a standards-compliant local ICS event."""

    def create_document(self, kind: str, title: str, content: str) -> ArtifactResult:
        """Save a professional local Markdown document."""

    def create_presentation(self, title: str, content: str) -> ArtifactResult:
        """Save a real local PowerPoint presentation."""

    def create_spreadsheet(self, title: str, rows: str) -> ArtifactResult:
        """Save a real local Excel workbook."""

    def generate_document(
        self, kind: str, title: str, brief: str
    ) -> ArtifactResult: ...

    def generate_presentation(self, title: str, brief: str) -> ArtifactResult: ...

    def generate_spreadsheet(self, title: str, brief: str) -> ArtifactResult: ...
