"""Crash-recovering process supervisor for the local Jarvis runtime."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from jarvis.core.config import get_settings
from jarvis.core.logging import configure_logging

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ManagedService:
    """A local process and the loopback endpoint proving it is healthy."""

    name: str
    command: tuple[str, ...]
    health_url: str
    working_directory: Path


class ProcessSupervisor:
    """Keep local services alive with bounded exponential restart backoff."""

    def __init__(
        self,
        services: Sequence[ManagedService],
        *,
        health_check: Callable[[str], bool] | None = None,
        poll_seconds: float = 5.0,
        maximum_backoff_seconds: float = 30.0,
        startup_timeout_seconds: float = 45.0,
        unhealthy_threshold: int = 3,
        log_directory: Path = Path("logs"),
    ) -> None:
        if unhealthy_threshold < 1:
            raise ValueError("unhealthy_threshold must be at least one")
        self._services = tuple(services)
        self._health_check = health_check or endpoint_is_healthy
        self._poll_seconds = poll_seconds
        self._maximum_backoff = maximum_backoff_seconds
        self._startup_timeout = startup_timeout_seconds
        self._unhealthy_threshold = unhealthy_threshold
        self._log_directory = log_directory
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._started_at: dict[str, float] = {}
        self._failures: dict[str, int] = {service.name: 0 for service in services}
        self._unhealthy_counts: dict[str, int] = {service.name: 0 for service in services}
        self._next_start: dict[str, float] = {service.name: 0.0 for service in services}
        self._stop = threading.Event()

    def request_stop(self, *_args: object) -> None:
        """Request a graceful supervisor shutdown."""
        self._stop.set()

    def run(self) -> None:
        """Monitor services until interrupted."""
        LOGGER.info("supervisor_started", extra={"services": len(self._services)})
        while not self._stop.is_set():
            self.check_once()
            self._stop.wait(self._poll_seconds)
        self._terminate_owned_processes()
        LOGGER.info("supervisor_stopped")

    def check_once(self) -> None:
        """Perform one deterministic health and recovery pass."""
        now = time.monotonic()
        for service in self._services:
            process = self._processes.get(service.name)
            if self._health_check(service.health_url):
                self._failures[service.name] = 0
                self._unhealthy_counts[service.name] = 0
                self._next_start[service.name] = 0.0
                continue
            if process is not None and process.poll() is None:
                started_at = self._started_at.get(service.name, now)
                if now - started_at < self._startup_timeout:
                    continue
                self._unhealthy_counts[service.name] += 1
                count = self._unhealthy_counts[service.name]
                LOGGER.warning(
                    "service_health_check_failed",
                    extra={
                        "service": service.name,
                        "consecutive_failures": count,
                        "failure_threshold": self._unhealthy_threshold,
                    },
                )
                if count < self._unhealthy_threshold:
                    continue
                LOGGER.error("service_unhealthy", extra={"service": service.name})
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                self._unhealthy_counts[service.name] = 0
            if now < self._next_start[service.name]:
                continue
            self._start(service, now)

    def _start(self, service: ManagedService, now: float) -> None:
        failures = self._failures[service.name]
        backoff = min(2.0**failures, self._maximum_backoff)
        try:
            self._log_directory.mkdir(parents=True, exist_ok=True)
            log_path = self._log_directory / f"supervisor-{service.name}.log"
            environment = os.environ.copy()
            if service.name == "ollama":
                environment["OLLAMA_NO_CLOUD"] = "true"
            with log_path.open("ab") as log_stream:
                process = subprocess.Popen(
                    service.command,
                    cwd=service.working_directory,
                    stdin=subprocess.DEVNULL,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except OSError as exc:
            LOGGER.error(
                "service_start_failed",
                extra={"service": service.name, "error": type(exc).__name__},
            )
        else:
            self._processes[service.name] = process
            self._started_at[service.name] = now
            self._unhealthy_counts[service.name] = 0
            LOGGER.info("service_started", extra={"service": service.name, "pid": process.pid})
        finally:
            self._failures[service.name] = failures + 1
            self._next_start[service.name] = now + backoff

    def _terminate_owned_processes(self) -> None:
        for name, process in self._processes.items():
            if process.poll() is None:
                LOGGER.info("service_stopping", extra={"service": name})
                process.terminate()
        for process in self._processes.values():
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


def endpoint_is_healthy(url: str) -> bool:
    """Return whether a loopback health endpoint responds successfully."""
    try:
        with urlopen(url, timeout=2) as response:
            status = int(response.status)
            return 200 <= status < 300
    except (OSError, URLError):
        return False


def build_services(project_root: Path) -> tuple[ManagedService, ...]:
    """Build local-only Ollama and Jarvis service definitions."""
    settings = get_settings()
    ollama = project_root / "tools" / "ollama" / "jarvis-ollama.exe"
    ollama_executable = str(ollama) if ollama.is_file() else shutil.which("ollama")
    services: list[ManagedService] = []
    if ollama_executable:
        services.append(
            ManagedService(
                "ollama",
                (ollama_executable, "serve"),
                "http://127.0.0.1:11434/api/tags",
                project_root,
            )
        )
    else:
        LOGGER.warning("ollama_executable_unavailable")
    project_python = project_root / ".venv" / "Scripts" / "python.exe"
    python_executable = str(project_python) if project_python.is_file() else sys.executable
    services.append(
        ManagedService(
            "jarvis",
            (python_executable, "-m", "jarvis.main"),
            f"http://127.0.0.1:{settings.port}/health",
            project_root,
        )
    )
    return tuple(services)


def run() -> None:
    """Start the production supervisor."""
    settings = get_settings()
    configure_logging(settings)
    project_root = Path.cwd()
    supervisor = ProcessSupervisor(build_services(project_root))
    signal.signal(signal.SIGINT, supervisor.request_stop)
    signal.signal(signal.SIGTERM, supervisor.request_stop)
    supervisor.run()


if __name__ == "__main__":
    run()
