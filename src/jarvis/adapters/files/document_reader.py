"""Bounded local extraction for common document formats."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from docx import Document
from pypdf import PdfReader

from jarvis.capabilities.documents import DocumentError


class LocalDocumentReader:
    """Read text, PDF, and Word files without executing embedded content."""

    _text_extensions: ClassVar[set[str]] = {
        ".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml",
        ".py", ".js", ".ts", ".java", ".go", ".rs", ".cs", ".cpp", ".sql",
        ".html", ".css", ".log",
    }

    def __init__(self, max_bytes: int = 10_000_000, max_characters: int = 40_000) -> None:
        self._max_bytes = max_bytes
        self._max_characters = max_characters

    def read(self, path: Path) -> str:
        """Extract bounded text from one existing regular file."""
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or resolved.stat().st_size > self._max_bytes:
            raise DocumentError("The document is missing or too large to read safely.")
        extension = resolved.suffix.casefold()
        try:
            if extension in self._text_extensions:
                text = self._read_text(resolved)
            elif extension == ".pdf":
                text = "\n".join(page.extract_text() or "" for page in PdfReader(resolved).pages)
            elif extension == ".docx":
                document = Document(str(resolved))
                text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            else:
                raise DocumentError(f"Unsupported document type: {extension or 'unknown'}")
        except DocumentError:
            raise
        except Exception as error:
            raise DocumentError("The document could not be read safely.") from error
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not normalized:
            raise DocumentError("The document contains no extractable text.")
        return normalized[: self._max_characters]

    @staticmethod
    def _read_text(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise DocumentError("The text encoding is not supported.")
