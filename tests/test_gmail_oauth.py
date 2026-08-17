"""Gmail OAuth adapter tests without network or real account access."""

from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import pytest

from jarvis.adapters.productivity.gmail_oauth import GmailOAuthGateway
from jarvis.capabilities.productivity import ProductivityError


class Request:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def execute(self) -> dict[str, Any]:
        return self.payload


class Messages:
    def __init__(self) -> None:
        self.sent: dict[str, str] | None = None

    def list(self, **_: Any) -> Request:
        return Request({"messages": [{"id": "newest"}]})

    def get(self, **_: Any) -> Request:
        return Request(
            {
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Manager <manager@example.com>"},
                        {"name": "Subject", "value": "Status"},
                        {"name": "Date", "value": "Today"},
                    ]
                }
            }
        )

    def send(self, *, body: dict[str, str], **_: Any) -> Request:
        self.sent = body
        return Request({"id": "sent"})


class Users:
    def __init__(self, messages: Messages) -> None:
        self._messages = messages

    def messages(self) -> Messages:
        return self._messages


class GmailService:
    def __init__(self) -> None:
        self.messages = Messages()

    def users(self) -> Users:
        return Users(self.messages)


def test_reads_metadata_and_sends_plain_text(tmp_path: Path) -> None:
    service = GmailService()
    gateway = GmailOAuthGateway(tmp_path / "token.json", service)

    latest = gateway.latest(5)
    gateway.send("Manager <manager@example.com>", "Re: Status", "Done today.")

    assert latest[0].sender == "Manager <manager@example.com>"
    assert latest[0].subject == "Status"
    assert service.messages.sent is not None
    encoded = service.messages.sent["raw"]
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(encoded))
    assert message["To"] == "manager@example.com"
    assert message["Subject"] == "Re: Status"
    assert "Done today." in message.get_content()


def test_rejects_unbounded_reads_and_invalid_recipient(tmp_path: Path) -> None:
    gateway = GmailOAuthGateway(tmp_path / "token.json", GmailService())

    with pytest.raises(ProductivityError, match="between 1 and 20"):
        gateway.latest(21)
    with pytest.raises(ProductivityError, match="recipient"):
        gateway.send("not-an-address", "Subject", "Body")
