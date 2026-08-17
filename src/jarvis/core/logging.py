"""Central structured logging configuration."""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any

from jarvis.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure bounded structured logs without recording user content."""
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    handlers = ["file"]
    if sys.stderr is not None:
        handlers.append("console")
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "level": settings.log_level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "level": settings.log_level,
                "filename": str((settings.log_dir / "jarvis.jsonl").resolve()),
                "maxBytes": 5_000_000,
                "backupCount": 3,
                "encoding": "utf-8",
                "delay": True,
            },
        },
        "root": {"handlers": handlers, "level": settings.log_level},
    }
    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""
    return logging.getLogger(name)
