"""Local OCR adapter tests without loading the production models."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.adapters.vision.rapidocr_reader import RapidOCRReader
from jarvis.capabilities.documents import DocumentError


class FakeEngine:
    def __init__(self, output: object | None = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error

    def __call__(self, source: object) -> object:
        if self.error is not None:
            raise self.error
        return self.output


def output() -> SimpleNamespace:
    return SimpleNamespace(
        txts=("Submit", "Email address"),
        scores=(0.97, 0.88),
        boxes=(
            ((10, 20), (110, 20), (110, 50), (10, 50)),
            ((10, 70), (180, 70), (180, 100), (10, 100)),
        ),
    )


def test_read_and_locate_use_local_engine(tmp_path: Path) -> None:
    image = tmp_path / "screen.png"
    image.write_bytes(b"png")
    reader = RapidOCRReader()
    reader._engine = FakeEngine(output())  # type: ignore[assignment]

    assert reader.read(image) == "Submit\nEmail address"
    regions = reader.locate(b"png", "submit")
    assert len(regions) == 1
    assert regions[0].text == "Submit"
    assert (regions[0].left, regions[0].top, regions[0].right, regions[0].bottom) == (
        10,
        20,
        110,
        50,
    )


def test_ocr_rejects_unsupported_and_empty_inputs(tmp_path: Path) -> None:
    unsupported = tmp_path / "screen.gif"
    unsupported.write_bytes(b"gif")
    reader = RapidOCRReader()
    with pytest.raises(DocumentError, match="supports"):
        reader.read(unsupported)
    assert reader.locate(b"png", "") == []


def test_ocr_wraps_engine_failure(tmp_path: Path) -> None:
    image = tmp_path / "screen.png"
    image.write_bytes(b"png")
    reader = RapidOCRReader()
    reader._engine = FakeEngine(error=RuntimeError("model failed"))  # type: ignore[assignment]
    with pytest.raises(DocumentError, match="OCR failed"):
        reader.read(image)
    with pytest.raises(DocumentError, match="screen OCR failed"):
        reader.locate(b"png", "Submit")
