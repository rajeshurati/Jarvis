from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from jarvis.adapters.automation.developer_commands import SafeDeveloperCommandService
from jarvis.capabilities.developer import DeveloperCommandError


def test_python_check_uses_fixed_command_without_shell(tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def run(command: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "Python 3.12.13\n", "")

    result = SafeDeveloperCommandService(tmp_path, run).run("python version")

    assert result.succeeded is True
    assert "Python 3.12.13" in result.summary
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == tmp_path.resolve()


def test_jarvis_test_command_is_predeclared(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, "1 failed", "")

    result = SafeDeveloperCommandService(tmp_path, run).run("jarvis tests")
    assert result.succeeded is False
    assert commands[0][1:] == ("-m", "pytest", "-q")


def test_arbitrary_dictated_command_is_rejected(tmp_path: Path) -> None:
    service = SafeDeveloperCommandService(tmp_path)
    with pytest.raises(DeveloperCommandError, match="not allowlisted"):
        service.run("delete everything")


def test_missing_external_tool_is_reported_without_execution(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "jarvis.adapters.automation.developer_commands.shutil.which", lambda _name: None
    )
    result = SafeDeveloperCommandService(tmp_path).run("docker version")
    assert result.succeeded is False
    assert "not installed" in result.summary
