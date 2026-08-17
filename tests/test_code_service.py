from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.application.code_service import LocalCodeService
from jarvis.capabilities.coding import CodeGenerationError
from jarvis.capabilities.language import LanguageMessage


class FakeModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[LanguageMessage] = []

    def complete(self, messages: list[LanguageMessage]) -> str:
        self.messages = messages
        return self.response


def test_generates_and_syntax_checks_python_without_execution(tmp_path: Path) -> None:
    model = FakeModel(
        "```python\ndef add(left: int, right: int) -> int:\n    return left + right\n```"
    )
    service = LocalCodeService(model, tmp_path)

    result = service.generate("Python", "calculator", "create an add function")

    assert result.path == tmp_path / "calculator.py"
    assert result.syntax_valid is True
    assert "def add" in result.path.read_text(encoding="utf-8")
    assert "source code only" in model.messages[0].content


def test_invalid_python_is_not_persisted(tmp_path: Path) -> None:
    service = LocalCodeService(FakeModel("def broken("), tmp_path)

    with pytest.raises(CodeGenerationError, match="syntax"):
        service.generate("python", "broken", "make broken code")

    assert list(tmp_path.iterdir()) == []


def test_unknown_language_is_rejected_before_model_call(tmp_path: Path) -> None:
    model = FakeModel("anything")
    service = LocalCodeService(model, tmp_path)
    with pytest.raises(CodeGenerationError, match="does not support"):
        service.generate("braincode", "sample", "do something")
    assert model.messages == []


def test_existing_code_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "sample.json").write_text("{}", encoding="utf-8")
    service = LocalCodeService(FakeModel('{"ok": true}'), tmp_path)
    result = service.generate("json", "sample", "make a status object")
    assert result.path.name == "sample-2.json"
    assert result.syntax_valid is True
