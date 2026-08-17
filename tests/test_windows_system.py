"""Bounded Windows system-control tests."""

from jarvis.adapters.automation.windows_system import WindowsSystemController


def test_opens_only_mapped_settings_page() -> None:
    commands: list[list[str]] = []
    controller = WindowsSystemController(commands.append, lambda _code: None)
    controller.open_settings("sound")
    assert commands == [["explorer.exe", "ms-settings:sound"]]


def test_volume_uses_media_key() -> None:
    codes: list[int] = []
    controller = WindowsSystemController(lambda _command: None, codes.append)
    controller.adjust_volume("up")
    assert codes == [0xAF]
