"""Local-first generation of email, calendar, and document artifacts."""

from __future__ import annotations

import os
import re
from csv import reader as csv_reader
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from io import BytesIO, StringIO
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from docx import Document
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from pptx import Presentation
from pptx.util import Inches, Pt

from jarvis.capabilities.language import LanguageMessage, LanguageModel
from jarvis.capabilities.productivity import ArtifactResult, ProductivityError


class LocalProductivityService:
    """Create interoperable work artifacts in a private local directory."""

    _email_pattern = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    _kinds: ClassVar[frozenset[str]] = frozenset(
        {
            "architecture document",
            "business document",
            "cover letter",
            "design document",
            "meeting notes",
            "report",
            "resume",
            "technical document",
        }
    )

    def __init__(
        self, output_directory: Path, model: LanguageModel | None = None
    ) -> None:
        self._output_directory = output_directory
        self._model = model

    def _generate(self, format_instruction: str, brief: str) -> str:
        if self._model is None:
            raise ProductivityError("Local content generation is unavailable.")
        clean_brief = re.sub(r"\s+", " ", brief).strip()
        if not 1 <= len(clean_brief) <= 4_000:
            raise ProductivityError("A valid artifact brief is required.")
        return self._model.complete(
            [
                LanguageMessage(
                    "system",
                    f"Create professional content from the user's brief. {format_instruction} "
                    "Return content only, without claiming the file already exists. Never invent "
                    "personal facts; mark missing facts clearly.",
                ),
                LanguageMessage("user", clean_brief),
            ]
        )

    def generate_document(self, kind: str, title: str, brief: str) -> ArtifactResult:
        content = self._generate(
            "Use concise headings and paragraphs suitable for an editable Word document.", brief
        )
        return self.create_document(kind, title, content)

    def generate_presentation(self, title: str, brief: str) -> ArtifactResult:
        content = self._generate(
            "Return 6 to 18 short slide points separated by semicolons.", brief
        )
        return self.create_presentation(title, content)

    def generate_spreadsheet(self, title: str, brief: str) -> ArtifactResult:
        content = self._generate(
            "Return CSV only. Include a header and practical rows; use semicolons between rows.",
            brief,
        )
        return self.create_spreadsheet(title, content)

    def _destination(self, title: str, suffix: str) -> Path:
        safe_name = re.sub(r"[^\w .-]", "", title, flags=re.UNICODE).strip(" .")
        safe_name = re.sub(r"\s+", " ", safe_name)[:80]
        if not safe_name:
            raise ProductivityError("The artifact title is not valid.")
        self._output_directory.mkdir(parents=True, exist_ok=True)
        candidate = self._output_directory / f"{safe_name}{suffix}"
        if candidate.exists():
            candidate = self._output_directory / (
                f"{safe_name}-{datetime.now():%Y%m%d-%H%M%S-%f}{suffix}"
            )
        return candidate

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ProductivityError("I could not save the local artifact.") from error

    def create_email_draft(self, recipient: str, subject: str, body: str) -> ArtifactResult:
        """Create an RFC-compliant EML draft without transmitting it."""
        recipient = recipient.strip()
        subject = " ".join(subject.split()).strip()
        body = body.strip()
        if not self._email_pattern.fullmatch(recipient):
            raise ProductivityError("The recipient email address is not valid.")
        if not 1 <= len(subject) <= 200 or not 1 <= len(body) <= 20_000:
            raise ProductivityError("Email subject or body length is not valid.")
        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        path = self._destination(subject, ".eml")
        self._atomic_write(path, message.as_bytes())
        return ArtifactResult("email draft", path)

    @staticmethod
    def _ical_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace(
            "\n", "\\n"
        )

    def create_calendar_event(
        self, title: str, starts_at: datetime, duration_minutes: int
    ) -> ArtifactResult:
        """Create an RFC 5545 calendar file using UTC timestamps."""
        title = " ".join(title.split()).strip()
        if not 1 <= len(title) <= 200 or not 1 <= duration_minutes <= 1_440:
            raise ProductivityError("Calendar title or duration is not valid.")
        if starts_at.tzinfo is None:
            starts_at = starts_at.astimezone()
        start = starts_at.astimezone(UTC)
        end = start + timedelta(minutes=duration_minutes)
        stamp = datetime.now(UTC)
        payload = "\r\n".join(
            (
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Local Jarvis//EN",
                "CALSCALE:GREGORIAN",
                "BEGIN:VEVENT",
                f"UID:{uuid4()}@local-jarvis",
                f"DTSTAMP:{stamp:%Y%m%dT%H%M%SZ}",
                f"DTSTART:{start:%Y%m%dT%H%M%SZ}",
                f"DTEND:{end:%Y%m%dT%H%M%SZ}",
                f"SUMMARY:{self._ical_escape(title)}",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            )
        )
        path = self._destination(title, ".ics")
        self._atomic_write(path, payload.encode("utf-8"))
        return ArtifactResult("calendar event", path)

    def create_document(self, kind: str, title: str, content: str) -> ArtifactResult:
        """Create a clean, editable Word document with creation metadata."""
        kind = " ".join(kind.casefold().split())
        title = " ".join(title.split()).strip()
        content = content.strip()
        if kind not in self._kinds:
            raise ProductivityError("That document type is not supported.")
        if not 1 <= len(title) <= 200 or not 1 <= len(content) <= 50_000:
            raise ProductivityError("Document title or content length is not valid.")
        document = Document()
        document.core_properties.title = title
        document.core_properties.subject = kind.title()
        document.add_heading(title, 0)
        metadata = document.add_paragraph()
        metadata.add_run("Type: ").bold = True
        metadata.add_run(kind.title())
        metadata.add_run("\nCreated locally: ").bold = True
        metadata.add_run(f"{datetime.now().astimezone():%Y-%m-%d %H:%M %Z}")
        document.add_heading("Content", level=1)
        for block in re.split(r"\n\s*\n", content):
            document.add_paragraph(block.strip())
        stream = BytesIO()
        document.save(stream)
        path = self._destination(title, ".docx")
        self._atomic_write(path, stream.getvalue())
        return ArtifactResult(kind, path)

    def create_presentation(self, title: str, content: str) -> ArtifactResult:
        """Create a clean, editable PPTX deck locally."""
        title, content = " ".join(title.split()), content.strip()
        if not 1 <= len(title) <= 200 or not 1 <= len(content) <= 30_000:
            raise ProductivityError("Presentation title or content length is not valid.")
        points = [item.strip(" -") for item in re.split(r"[;\n]+", content) if item.strip()]
        if not points:
            raise ProductivityError("Presentation content is required.")
        deck = Presentation()
        deck.slide_width = Inches(13.333)
        deck.slide_height = Inches(7.5)
        title_slide = deck.slides.add_slide(deck.slide_layouts[0])
        title_slide.shapes.title.text = title
        title_slide.placeholders[1].text = "Created locally by Jarvis"
        for offset in range(0, min(len(points), 30), 6):
            slide = deck.slides.add_slide(deck.slide_layouts[1])
            slide.shapes.title.text = title if offset == 0 else f"{title} - continued"
            frame = slide.placeholders[1].text_frame
            frame.clear()
            for index, point in enumerate(points[offset : offset + 6]):
                paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                paragraph.text = point[:500]
                paragraph.font.size = Pt(24)
        stream = BytesIO()
        deck.save(stream)
        path = self._destination(title, ".pptx")
        self._atomic_write(path, stream.getvalue())
        return ArtifactResult("presentation", path)

    def create_spreadsheet(self, title: str, rows: str) -> ArtifactResult:
        """Create a styled, editable XLSX workbook from semicolon-separated rows."""
        title, rows = " ".join(title.split()), rows.strip()
        if not 1 <= len(title) <= 200 or not 1 <= len(rows) <= 50_000:
            raise ProductivityError("Spreadsheet title or rows are not valid.")
        parsed = list(csv_reader(StringIO(rows.replace(";", "\n"))))[:1_000]
        if not parsed or any(len(row) > 50 for row in parsed):
            raise ProductivityError("Spreadsheet rows are not valid.")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = re.sub(r"[\\/*?:\[\]]", "", title)[:31] or "Jarvis"
        for row in parsed:
            sheet.append([cell.strip()[:2_000] for cell in row])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(
                max(12, max(len(str(cell.value or "")) for cell in column) + 2), 48
            )
        stream = BytesIO()
        workbook.save(stream)
        path = self._destination(title, ".xlsx")
        self._atomic_write(path, stream.getvalue())
        return ArtifactResult("spreadsheet", path)
