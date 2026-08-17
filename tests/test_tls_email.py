"""TLS email adapter tests with isolated protocol clients."""

import imaplib
import smtplib
from email.message import EmailMessage

import pytest

from jarvis.adapters.productivity.tls_email import TLSMailGateway
from jarvis.capabilities.productivity import ProductivityError


class FakeSMTP:
    def __init__(self) -> None:
        self.login_args: tuple[str, str] | None = None
        self.message: EmailMessage | None = None

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        self.message = message


class FakeIMAP:
    def __enter__(self) -> "FakeIMAP":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        return None

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        return "OK", [b"2"]

    def search(self, charset: object, criterion: str) -> tuple[str, list[bytes]]:
        return "OK", [b"1 2"]

    def fetch(self, identifier: bytes, query: str) -> tuple[str, list[object]]:
        header = (
            b"From: Manager <manager@example.com>\r\n"
            b"Subject: =?utf-8?q?Weekly_update?=\r\n"
            b"Date: Fri, 1 Aug 2026 10:00:00 +0000\r\n\r\n"
        )
        return "OK", [(b"headers", header)]


def gateway() -> TLSMailGateway:
    return TLSMailGateway(
        "me@example.com",
        "me@example.com",
        "secret",
        "smtp.example.com",
        465,
        "imap.example.com",
        993,
    )


def test_send_uses_tls_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeSMTP()
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *args, **kwargs: client)

    gateway().send("person@example.com", "Weekly status", "Everything is done.")

    assert client.login_args == ("me@example.com", "secret")
    assert client.message is not None
    assert client.message["To"] == "person@example.com"


def test_latest_reads_only_bounded_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda *args, **kwargs: FakeIMAP())

    messages = gateway().latest(2)

    assert len(messages) == 2
    assert messages[0].sender == "Manager <manager@example.com>"
    assert messages[0].subject == "Weekly update"


def test_mail_protocol_errors_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_smtp(*args: object, **kwargs: object) -> object:
        raise OSError("private network detail")

    def fail_imap(*args: object, **kwargs: object) -> object:
        raise imaplib.IMAP4.error("private server detail")

    monkeypatch.setattr(smtplib, "SMTP_SSL", fail_smtp)
    with pytest.raises(ProductivityError, match="could not be sent"):
        gateway().send("person@example.com", "Status", "Body")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", fail_imap)
    with pytest.raises(ProductivityError, match="could not be read"):
        gateway().latest(1)
    with pytest.raises(ProductivityError, match="between 1 and 20"):
        gateway().latest(21)
