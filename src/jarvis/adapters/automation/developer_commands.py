"""No-shell execution of explicitly allowlisted developer checks."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from jarvis.capabilities.developer import (
    DeveloperCommandError,
    DeveloperCommandResult,
)


class SafeDeveloperCommandService:
    """Run trusted diagnostics without evaluating user-provided command text."""

    _external_commands: ClassVar[dict[str, tuple[str, ...]]] = {
        "git version": ("git", "--version"),
        "docker version": ("docker", "--version"),
        "kubectl version": ("kubectl", "version", "--client"),
        "terraform version": ("terraform", "version"),
    }

    def __init__(
        self,
        project_root: Path,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._root = project_root.resolve()
        self._runner = runner

    def run(self, name: str) -> DeveloperCommandResult:
        normalized = re.sub(r"\s+", " ", name.casefold()).strip()
        command: tuple[str, ...]
        if normalized == "jarvis tests":
            command = (sys.executable, "-m", "pytest", "-q")
            timeout = 180
        elif normalized == "jarvis lint":
            command = (sys.executable, "-m", "ruff", "check", "src", "tests")
            timeout = 60
        elif normalized == "jarvis type check":
            command = (sys.executable, "-m", "mypy", "src/jarvis")
            timeout = 120
        elif normalized == "python version":
            command = (sys.executable, "--version")
            timeout = 15
        elif normalized in self._external_commands:
            requested = self._external_commands[normalized]
            executable = shutil.which(requested[0])
            if executable is None:
                return DeveloperCommandResult(
                    normalized, False, f"{requested[0]} is not installed or not on PATH."
                )
            command = (executable, *requested[1:])
            timeout = 30
        else:
            raise DeveloperCommandError("That developer command is not allowlisted.")
        try:
            completed = self._runner(
                command,
                cwd=self._root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DeveloperCommandError(f"The {normalized} command could not complete.") from error
        output = " ".join((completed.stdout or completed.stderr).split())[:500]
        summary = output or f"Exit code {completed.returncode}."
        return DeveloperCommandResult(normalized, completed.returncode == 0, summary)
