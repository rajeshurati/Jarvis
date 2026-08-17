"""Minimal localhost-only Ollama chat adapter."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from jarvis.capabilities.language import LanguageMessage, LanguageModelError


class OllamaLanguageModel:
    """Call an Ollama model through its loopback HTTP API."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        *,
        maximum_tokens: int = 96,
        context_window: int = 2_048,
    ) -> None:
        self._chat_url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._maximum_tokens = maximum_tokens
        self._context_window = context_window

    def complete(self, messages: list[LanguageMessage]) -> str:
        """Generate one non-streaming response entirely through localhost."""
        payload = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": message.role, "content": message.content} for message in messages
                ],
                "stream": False,
                "think": False,
                "keep_alive": "15m",
                "options": {
                    "temperature": 0.2,
                    "num_ctx": self._context_window,
                    "num_predict": self._maximum_tokens,
                },
            }
        ).encode("utf-8")
        request = Request(
            self._chat_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise LanguageModelError("The local language model is unavailable") from error
        content = body.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise LanguageModelError("The local language model returned an empty response")
        return content.strip()
