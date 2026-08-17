"""Process entry point for the Local Jarvis API."""

from __future__ import annotations

import uvicorn

from jarvis.core.config import get_settings


def run() -> None:
    """Start the localhost API using validated application settings."""
    settings = get_settings()
    uvicorn.run(
        "jarvis.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    run()
