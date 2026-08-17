from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.supervisor import ManagedService, ProcessSupervisor


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 42
        self.return_code: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = 0

    def wait(self, timeout: float) -> int:
        del timeout
        return self.return_code or 0

    def kill(self) -> None:
        self.killed = True
        self.return_code = -1


def service() -> ManagedService:
    return ManagedService(
        "jarvis", ("python", "-m", "jarvis.main"), "http://local/health", Path.cwd()
    )


def test_supervisor_does_not_start_a_healthy_service(monkeypatch: Any) -> None:
    starts: list[object] = []
    monkeypatch.setattr(
        "jarvis.supervisor.subprocess.Popen", lambda *args, **kwargs: starts.append(args)
    )
    supervisor = ProcessSupervisor((service(),), health_check=lambda _url: True)

    supervisor.check_once()

    assert starts == []


def test_supervisor_starts_and_recovers_a_failed_service(monkeypatch: Any) -> None:
    processes: list[FakeProcess] = []

    def start(*_args: object, **_kwargs: object) -> FakeProcess:
        process = FakeProcess()
        processes.append(process)
        return process

    now = [10.0]
    monkeypatch.setattr("jarvis.supervisor.subprocess.Popen", start)
    monkeypatch.setattr("jarvis.supervisor.time.monotonic", lambda: now[0])
    supervisor = ProcessSupervisor((service(),), health_check=lambda _url: False)

    supervisor.check_once()
    supervisor.check_once()
    assert len(processes) == 1

    processes[0].return_code = 1
    now[0] = 11.0
    supervisor.check_once()
    assert len(processes) == 2


def test_supervisor_terminates_only_processes_it_started(monkeypatch: Any) -> None:
    process = FakeProcess()
    monkeypatch.setattr("jarvis.supervisor.subprocess.Popen", lambda *_args, **_kwargs: process)
    supervisor = ProcessSupervisor((service(),), health_check=lambda _url: False)
    supervisor.check_once()

    supervisor.request_stop()
    supervisor._terminate_owned_processes()

    assert process.terminated is True
    assert process.killed is False


def test_supervisor_ignores_transient_health_check_failure(monkeypatch: Any) -> None:
    process = FakeProcess()
    health = iter((False, True))
    now = [10.0]
    monkeypatch.setattr("jarvis.supervisor.subprocess.Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr("jarvis.supervisor.time.monotonic", lambda: now[0])
    supervisor = ProcessSupervisor(
        (service(),),
        health_check=lambda _url: next(health),
        startup_timeout_seconds=0,
        unhealthy_threshold=3,
    )
    supervisor.check_once()
    now[0] = 11.0
    supervisor.check_once()

    assert process.terminated is False


def test_supervisor_restarts_after_consecutive_health_failures(monkeypatch: Any) -> None:
    processes: list[FakeProcess] = []

    def start(*_args: object, **_kwargs: object) -> FakeProcess:
        process = FakeProcess()
        processes.append(process)
        return process

    now = [10.0]
    monkeypatch.setattr("jarvis.supervisor.subprocess.Popen", start)
    monkeypatch.setattr("jarvis.supervisor.time.monotonic", lambda: now[0])
    supervisor = ProcessSupervisor(
        (service(),),
        health_check=lambda _url: False,
        startup_timeout_seconds=0,
        unhealthy_threshold=3,
    )

    supervisor.check_once()
    for timestamp in (11.0, 12.0):
        now[0] = timestamp
        supervisor.check_once()
        assert processes[0].terminated is False

    now[0] = 13.0
    supervisor.check_once()

    assert processes[0].terminated is True
    assert len(processes) == 2


def test_supervisor_rejects_invalid_health_failure_threshold() -> None:
    try:
        ProcessSupervisor((service(),), unhealthy_threshold=0)
    except ValueError as error:
        assert "at least one" in str(error)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("Expected invalid unhealthy threshold to be rejected")
