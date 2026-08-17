"""TLS-only SMTP and IMAP email adapter."""

from __future__ import annotations

import imaplib
import smtplib
import ssl
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser

from jarvis.capabilities.productivity import EmailSummary, ProductivityError


class TLSMailGateway:
    """Access one user-configured email account without persisting credentials."""

    def __init__(
        self,
        address: str,
        username: str,
        password: str,
        smtp_host: str,
        smtp_port: int,
        imap_host: str,
        imap_port: int,
        timeout_seconds: float = 20,
    ) -> None:
        self._address = address
        self._username = username
        self._password = password
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._timeout = timeout_seconds

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Send one plain-text message over SMTP implicit TLS."""
        message = EmailMessage()
        message["From"] = self._address
        message["To"] = recipient
        message["Subject"] = " ".join(subject.split())[:200]
        message.set_content(body[:20_000])
        try:
            with smtplib.SMTP_SSL(
                self._smtp_host,
                self._smtp_port,
                timeout=self._timeout,
                context=ssl.create_default_context(),
            ) as client:
                client.login(self._username, self._password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            raise ProductivityError(
                "The email could not be sent through the configured account."
            ) from error

    @staticmethod
    def _header(value: str | None) -> str:
        decoded: list[str] = []
        for part, encoding in decode_header(value or ""):
            if isinstance(part, bytes):
                decoded.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return "".join(decoded).replace("\r", " ").replace("\n", " ").strip()[:300]

    def latest(self, limit: int) -> list[EmailSummary]:
        """Fetch only headers for a bounded number of newest messages."""
        if not 1 <= limit <= 20:
            raise ProductivityError("Email read limit must be between 1 and 20.")
        try:
            with imaplib.IMAP4_SSL(
                self._imap_host,
                self._imap_port,
                ssl_context=ssl.create_default_context(),
                timeout=self._timeout,
            ) as client:
                client.login(self._username, self._password)
                status, _ = client.select("INBOX", readonly=True)
                if status != "OK":
                    raise ProductivityError("The configured inbox is unavailable.")
                status, data = client.search(None, "ALL")
                if status != "OK" or not data:
                    return []
                identifiers = data[0].split()[-limit:]
                summaries: list[EmailSummary] = []
                for identifier in reversed(identifiers):
                    status, payload = client.fetch(
                        identifier, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
                    )
                    if status != "OK" or not payload or not isinstance(payload[0], tuple):
                        continue
                    message = BytesParser(policy=policy.default).parsebytes(payload[0][1])
                    summaries.append(
                        EmailSummary(
                            self._header(message.get("From")),
                            self._header(message.get("Subject")) or "No subject",
                            self._header(message.get("Date")),
                        )
                    )
                return summaries
        except ProductivityError:
            raise
        except (OSError, imaplib.IMAP4.error) as error:
            raise ProductivityError("The configured mailbox could not be read.") from error
