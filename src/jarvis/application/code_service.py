"""Local-model code generation with non-executing validation."""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from jarvis.capabilities.coding import CodeArtifact, CodeGenerationError
from jarvis.capabilities.language import LanguageMessage, LanguageModel


class LocalCodeService:
    """Create source files locally; never execute model-generated code."""

    _languages: ClassVar[dict[str, tuple[str, str]]] = {
        "python": (".py", "Python 3.12"),
        "javascript": (".js", "modern JavaScript"),
        "typescript": (".ts", "strict TypeScript"),
        "java": (".java", "Java 21"),
        "go": (".go", "Go"),
        "rust": (".rs", "Rust"),
        "c sharp": (".cs", "C#"),
        "c#": (".cs", "C#"),
        "c plus plus": (".cpp", "C++20"),
        "c++": (".cpp", "C++20"),
        "sql": (".sql", "portable SQL"),
        "powershell": (".ps1", "PowerShell 7"),
        "bash": (".sh", "Bash"),
        "terraform": (".tf", "Terraform HCL"),
        "yaml": (".yaml", "YAML 1.2"),
        "github actions": (".yml", "GitHub Actions workflow YAML"),
        "json": (".json", "strict JSON"),
    }

    def __init__(self, model: LanguageModel, output_directory: Path) -> None:
        self._model = model
        self._output_directory = output_directory

    def generate(self, language: str, title: str, request: str) -> CodeArtifact:
        normalized_language = " ".join(language.casefold().split())
        if normalized_language not in self._languages:
            raise CodeGenerationError(f"Code generation does not support {language} yet.")
        extension, language_label = self._languages[normalized_language]
        safe_title = re.sub(r"[^A-Za-z0-9_. -]", "", title).strip(" .")[:80]
        description = re.sub(r"\s+", " ", request).strip()
        if not safe_title or not 1 <= len(description) <= 4_000:
            raise CodeGenerationError("A valid code title and request are required.")
        response = self._model.complete(
            [
                LanguageMessage(
                    "system",
                    f"Write production-quality {language_label}. Return source code only, with "
                    "no Markdown fences and no explanation. Include input validation, clear names, "
                    "errors, and useful comments. Never embed credentials or claim the code ran.",
                ),
                LanguageMessage("user", description),
            ]
        )
        source = self._strip_fence(response)
        if not source or len(source) > 100_000:
            raise CodeGenerationError("The local model returned invalid source code.")
        self._output_directory.mkdir(parents=True, exist_ok=True)
        destination = self._unique_destination(safe_title, extension)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(source.rstrip() + "\n", encoding="utf-8")
            syntax_valid = self._validate(normalized_language, source)
            if syntax_valid is False:
                raise CodeGenerationError("Generated code failed local syntax validation.")
            os.replace(temporary, destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise CodeGenerationError("I could not save the generated code locally.") from error
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return CodeArtifact(destination, normalized_language, syntax_valid)

    def _unique_destination(self, title: str, extension: str) -> Path:
        stem = title[: -len(extension)] if title.casefold().endswith(extension) else title
        destination = self._output_directory / f"{stem}{extension}"
        counter = 2
        while destination.exists():
            destination = self._output_directory / f"{stem}-{counter}{extension}"
            counter += 1
        return destination

    @staticmethod
    def _strip_fence(response: str) -> str:
        value = response.strip()
        match = re.fullmatch(r"```(?:[\w+#.-]+)?\s*\n?(.*?)\n?```", value, re.S)
        return match.group(1).strip() if match else value

    @staticmethod
    def _validate(language: str, source: str) -> bool | None:
        try:
            if language == "python":
                ast.parse(source)
                return True
            if language == "json":
                json.loads(source)
                return True
        except (SyntaxError, json.JSONDecodeError):
            return False
        return None
