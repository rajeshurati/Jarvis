"""Gmail API adapter authenticated with a revocable local OAuth token."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from jarvis.capabilities.productivity import EmailSummary, ProductivityError

GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)


class GmailOAuthGateway:
    """Read and send Gmail without storing the Google account password."""

    def __init__(self, token_file: Path, service: Any | None = None) -> None:
        self._token_file = token_file
        self._service = service or self._build_service()

    def _build_service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build  # type: ignore[import-untyped]
        except ImportError as error:
            raise ProductivityError(
                "Gmail OAuth support is not installed. Install the gmail dependency group."
            ) from error
        try:
            credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(self._token_file), list(GMAIL_SCOPES)
            )
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self._save_token(credentials.to_json())
            if not credentials.valid:
                raise ProductivityError(
                    "Gmail authorization expired. Run jarvis-google-auth again."
                )
            return build("gmail", "v1", credentials=credentials, cache_discovery=False)
        except ProductivityError:
            raise
        except Exception as error:
            raise ProductivityError(
                "Gmail authorization could not be loaded. Run jarvis-google-auth again."
            ) from error

    def _save_token(self, payload: str) -> None:
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        self._token_file.write_text(payload, encoding="utf-8")
        self._token_file.chmod(0o600)

    def latest(self, limit: int) -> list[EmailSummary]:
        """Fetch bounded metadata for the newest inbox messages."""
        return self._summaries(limit=limit)

    def search(self, query: str, limit: int = 20) -> list[EmailSummary]:
        """Search inbox messages using Gmail's server-side search."""
        cleaned = " ".join(query.split())[:200]
        if not cleaned:
            return []
        return self._summaries(limit=limit, query=f'in:inbox "{cleaned}"')

    def _summaries(self, limit: int, query: str | None = None) -> list[EmailSummary]:
        """Fetch bounded Gmail metadata, optionally using a search query."""
        if not 1 <= limit <= 20:
            raise ProductivityError("Email read limit must be between 1 and 20.")
        try:
            request = {"userId": "me", "labelIds": ["INBOX"], "maxResults": limit}
            if query:
                request["q"] = query
            response = self._service.users().messages().list(**request).execute()
            summaries: list[EmailSummary] = []
            for item in response.get("messages", []):
                message = (
                    self._service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=item["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )
                headers = {
                    header.get("name", "").casefold(): str(header.get("value", ""))[:300]
                    for header in message.get("payload", {}).get("headers", [])
                }
                summaries.append(
                    EmailSummary(
                        headers.get("from", "Unknown sender"),
                        headers.get("subject", "No subject"),
                        headers.get("date", ""),
                        str(item["id"]),
                    )
                )
            return summaries
        except Exception as error:
            raise ProductivityError("The Gmail inbox could not be read.") from error

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Send a confirmed plain-text message through the Gmail API."""
        address = parseaddr(recipient)[1]
        if not address or "@" not in address:
            raise ProductivityError("The recipient email address is not valid.")
        message = EmailMessage()
        message["To"] = address
        message["Subject"] = " ".join(subject.split())[:200]
        message.set_content(body[:20_000])
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            (
                self._service.users()
                .messages()
                .send(userId="me", body={"raw": encoded})
                .execute()
            )
        except Exception as error:
            raise ProductivityError("The email could not be sent through Gmail.") from error
