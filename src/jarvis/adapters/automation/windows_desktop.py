"""Conservative Windows desktop commands."""

from __future__ import annotations

import re
import shutil
import subprocess
import webbrowser
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote_plus, urlparse

from jarvis.capabilities.automation import ActionResult, AutomationError


class WindowsDesktopAutomation:
    """Open an allowlisted application or website without shell evaluation."""

    _applications: ClassVar[dict[str, list[str]]] = {
        "calculator": ["calc.exe"],
        "notepad": ["notepad.exe"],
        "file explorer": ["explorer.exe"],
        "explorer": ["explorer.exe"],
        "paint": ["mspaint.exe"],
        "settings": ["cmd.exe", "/d", "/c", "start", "", "ms-settings:"],
    }
    _discoverable_applications: ClassVar[dict[str, tuple[str, ...]]] = {
        "visual studio code": ("code.exe",),
        "vs code": ("code.exe",),
        "vscode": ("code.exe",),
        "powershell": ("pwsh.exe", "powershell.exe"),
        "terminal": ("wt.exe",),
        "windows terminal": ("wt.exe",),
        "word": ("winword.exe",),
        "microsoft word": ("winword.exe",),
        "excel": ("excel.exe",),
        "powerpoint": ("powerpnt.exe",),
        "outlook": ("outlook.exe",),
        "chrome": ("chrome.exe",),
        "google chrome": ("chrome.exe",),
        "edge": ("msedge.exe",),
        "microsoft edge": ("msedge.exe",),
        "firefox": ("firefox.exe",),
        "teams": ("ms-teams.exe", "teams.exe"),
        "spotify": ("spotify.exe",),
    }
    _websites: ClassVar[dict[str, str]] = {
        "google": "https://www.google.com/",
        "youtube": "https://www.youtube.com/",
        "gmail": "https://mail.google.com/",
        "github": "https://github.com/",
        "linkedin": "https://www.linkedin.com/",
        "outlook mail": "https://outlook.office.com/mail/",
        "calendar": "https://calendar.google.com/",
        "google drive": "https://drive.google.com/",
        "stackoverflow": "https://stackoverflow.com/",
    }

    @staticmethod
    def _resolve_executable(candidates: tuple[str, ...]) -> str | None:
        """Resolve only predeclared executable names; never execute dictated paths."""
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
            try:
                import winreg

                for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    key_path = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{candidate}"
                    try:
                        with winreg.OpenKey(root, key_path) as key:
                            value, _kind = winreg.QueryValueEx(key, "")
                        path = Path(str(value).strip('"'))
                        if path.is_file():
                            return str(path)
                    except OSError:
                        continue
            except ImportError:  # pragma: no cover - Windows runtime always provides winreg
                return None
        return None

    @staticmethod
    def _safe_https_url(value: str) -> str | None:
        candidate = value.strip()
        if not re.match(r"^[a-z][a-z0-9+.-]*://", candidate, re.I):
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        hostname = parsed.hostname.rstrip(".")
        if "." not in hostname or any(char.isspace() for char in hostname):
            return None
        try:
            address = ip_address(hostname)
        except ValueError:
            pass
        else:
            if not address.is_global:
                return None
        return candidate

    def try_execute(self, command: str) -> ActionResult | None:
        """Execute a recognized read-only or reversible desktop action."""
        normalized = re.sub(r"\s+", " ", command.strip().lower()).rstrip(".!?")
        if normalized in {"what time is it", "tell me the time", "time"}:
            return ActionResult("read_time", f"It is {datetime.now():%I:%M %p}.")
        if normalized in {"what is the date", "tell me the date", "date"}:
            return ActionResult("read_date", f"Today is {datetime.now():%A, %B %d, %Y}.")
        target = normalized.removeprefix("please ").removeprefix("open ")
        if normalized.startswith(("open ", "please open ")) and target in self._applications:
            try:
                subprocess.Popen(self._applications[target], close_fds=True)
            except OSError as error:
                raise AutomationError(f"I could not open {target}") from error
            return ActionResult("open_application", f"Opening {target}.")
        if (
            normalized.startswith(("open ", "please open "))
            and target in self._discoverable_applications
        ):
            executable = self._resolve_executable(self._discoverable_applications[target])
            if executable is None:
                return ActionResult(
                    "application_not_installed", f"I could not find {target} on this laptop."
                )
            try:
                subprocess.Popen([executable], close_fds=True)
            except OSError as error:
                raise AutomationError(f"I could not open {target}") from error
            return ActionResult("open_application", f"Opening {target}.")
        if normalized.startswith(("open ", "please open ")) and target in self._websites:
            new_window = 0 if target == "gmail" else 2
            if not webbrowser.open(self._websites[target], new=new_window):
                raise AutomationError(f"I could not open {target}")
            return ActionResult("open_website", f"Opening {target}.")
        web_search = re.fullmatch(r"(?:search|look up) (?:the web )?for (.+)", normalized)
        if web_search:
            query = web_search.group(1).strip()
            if not 1 <= len(query) <= 500:
                return None
            if not webbrowser.open(
                f"https://www.google.com/search?q={quote_plus(query)}", new=2
            ):
                raise AutomationError("I could not open the web search")
            return ActionResult("web_search", f"Searching the web for {query}.")
        website = re.fullmatch(r"open (?:the )?(?:website|site) (\S+)", normalized)
        if website:
            url = self._safe_https_url(website.group(1))
            if url is None:
                return ActionResult(
                    "invalid_website", "I can open only a valid public HTTPS website."
                )
            new_window = 0 if urlparse(url).hostname == "mail.google.com" else 2
            if not webbrowser.open(url, new=new_window):
                raise AutomationError("I could not open that website")
            return ActionResult("open_website", f"Opening {url}.")
        return None
