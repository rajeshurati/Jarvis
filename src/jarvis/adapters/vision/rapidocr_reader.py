"""RapidOCR adapter for local image text extraction."""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import cast

from rapidocr import RapidOCR
from rapidocr.utils.output import RapidOCROutput

from jarvis.capabilities.documents import DocumentError
from jarvis.capabilities.vision import ScreenTextRegion


class RapidOCRReader:
    """Run OCR locally with lazily initialized ONNX models."""

    def __init__(self) -> None:
        self._engine: RapidOCR | None = None

    def read(self, path: Path) -> str:
        """Extract text from one bounded image file."""
        resolved = path.resolve(strict=True)
        if resolved.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            raise DocumentError("OCR supports PNG, JPEG, WebP, and BMP images.")
        if resolved.stat().st_size > 20_000_000:
            raise DocumentError("The image is too large for local OCR.")
        try:
            self._engine = self._engine or RapidOCR()
            result = cast(RapidOCROutput, self._engine(resolved))
        except Exception as error:
            raise DocumentError("Local OCR failed for that image.") from error
        text = "\n".join(result.txts or ()).strip()
        if not text:
            raise DocumentError("No readable text was detected in that image.")
        return text[:20_000]

    def locate(self, image: bytes, query: str) -> list[ScreenTextRegion]:
        """Locate matching text boxes in an in-memory PNG using local OCR."""
        clean_query = " ".join(query.casefold().split())
        if not clean_query or len(clean_query) > 200:
            return []
        try:
            self._engine = self._engine or RapidOCR()
            result = cast(RapidOCROutput, self._engine(image))
        except Exception as error:
            raise DocumentError("Local screen OCR failed.") from error

        regions: list[ScreenTextRegion] = []
        boxes = result.boxes
        for text, score, box in zip(
            result.txts or (),
            result.scores or (),
            boxes if boxes is not None else (),
            strict=False,
        ):
            normalized = " ".join(text.casefold().split())
            fuzzy_score = max(
                [SequenceMatcher(None, clean_query, normalized).ratio()]
                + [
                    SequenceMatcher(None, clean_query, token.strip(" ,.:;()[]")).ratio()
                    for token in normalized.split()
                ]
            )
            if (
                clean_query not in normalized
                and normalized not in clean_query
                and fuzzy_score < 0.68
            ):
                continue
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            regions.append(
                ScreenTextRegion(
                    text=text,
                    confidence=float(score),
                    left=round(min(xs)),
                    top=round(min(ys)),
                    right=round(max(xs)),
                    bottom=round(max(ys)),
                )
            )
        return sorted(
            regions,
            key=lambda region: (
                " ".join(region.text.casefold().split()) == clean_query,
                region.confidence,
            ),
            reverse=True,
        )
