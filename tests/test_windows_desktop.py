from __future__ import annotations

from typing import Any

from jarvis.adapters.automation.windows_desktop import WindowsDesktopAutomation


def test_opens_a_discovered_application_without_shell(monkeypatch: Any) -> None:
    launched: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        WindowsDesktopAutomation,
        "_resolve_executable",
        staticmethod(lambda _candidates: r"C:\Program Files\App\code.exe"),
    )
    monkeypatch.setattr(
        "jarvis.adapters.automation.windows_desktop.subprocess.Popen",
        lambda command, close_fds: launched.append((command, close_fds)),
    )

    result = WindowsDesktopAutomation().try_execute("open VS Code")

    assert result and result.action == "open_application"
    assert launched == [([r"C:\Program Files\App\code.exe"], True)]


def test_reports_an_application_that_is_not_installed(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        WindowsDesktopAutomation,
        "_resolve_executable",
        staticmethod(lambda _candidates: None),
    )
    result = WindowsDesktopAutomation().try_execute("open Excel")
    assert result and result.action == "application_not_installed"


def test_opens_public_https_website_and_web_search(monkeypatch: Any) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        "jarvis.adapters.automation.windows_desktop.webbrowser.open",
        lambda url, new: opened.append(url) or new == 2,
    )
    website = WindowsDesktopAutomation().try_execute("open website example.com/docs")
    search = WindowsDesktopAutomation().try_execute("search the web for local AI privacy")

    assert website and website.action == "open_website"
    assert search and search.action == "web_search"
    assert opened == [
        "https://example.com/docs",
        "https://www.google.com/search?q=local+ai+privacy",
    ]


def test_rejects_local_http_and_credential_urls(monkeypatch: Any) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        "jarvis.adapters.automation.windows_desktop.webbrowser.open",
        lambda url, new: opened.append(url) or True,
    )
    local = WindowsDesktopAutomation().try_execute("open website http://127.0.0.1/admin")
    credentials = WindowsDesktopAutomation().try_execute(
        "open website https://user:password@example.com"
    )
    assert local and local.action == "invalid_website"
    assert credentials and credentials.action == "invalid_website"
    assert opened == []
