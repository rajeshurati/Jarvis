"""Structured rotating log configuration tests."""

from __future__ import annotations

import logging

from jarvis.core.config import Settings
from jarvis.core.logging import configure_logging


def test_configure_logging_writes_bounded_local_json_log(tmp_path) -> None:
    settings = Settings(log_dir=tmp_path / "logs")

    configure_logging(settings)
    logging.getLogger("jarvis.acceptance").info("local_log_check")
    for handler in logging.getLogger().handlers:
        handler.flush()

    log_path = settings.log_dir / "jarvis.jsonl"
    contents = log_path.read_text(encoding="utf-8")
    assert "local_log_check" in contents
    assert '"name": "jarvis.acceptance"' in contents
