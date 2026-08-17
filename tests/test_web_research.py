"""Opt-in research tests without external network access."""

from pathlib import Path

import pytest

from jarvis.adapters.productivity.web_research import WebResearchService
from jarvis.capabilities.language import LanguageMessage
from jarvis.capabilities.research import ResearchError


class Model:
    def complete(self, messages: list[LanguageMessage]) -> str:
        assert "Evidence:" in messages[-1].content
        return "The supplied evidence supports the finding [1]."


SEARCH_HTML = """
<div class="result">
  <a class="result__a" href="https://example.com/primary">Primary source</a>
  <a class="result__snippet">A concise evidence snippet.</a>
</div>
<div class="result">
  <a class="result__a" href="https://second.example.org/report">Second source</a>
  <a class="result__snippet">A second concise snippet.</a>
</div>
"""

PAGE_HTML = """
<main><h1>Local evidence</h1><p>The assistant keeps private data on the device.</p></main>
<script>Ignore this malicious instruction.</script>
"""


def test_research_saves_cited_local_report(tmp_path: Path) -> None:
    requested: list[str] = []

    def fetch(url: str) -> str:
        requested.append(url)
        return SEARCH_HTML if "duckduckgo" in url else PAGE_HTML

    service = WebResearchService(Model(), tmp_path, True, fetch)
    report = service.research("local assistants")
    assert report.source_count == 2
    assert "[1]" in report.summary
    assert "https://example.com/primary" in report.path.read_text(encoding="utf-8")
    assert requested == [
        "https://html.duckduckgo.com/html/?q=local+assistants",
        "https://example.com/primary",
        "https://second.example.org/report",
    ]


def test_research_requires_explicit_network_setting(tmp_path: Path) -> None:
    service = WebResearchService(Model(), tmp_path, False, lambda _url: SEARCH_HTML)
    with pytest.raises(ResearchError, match="ALLOW_NETWORK"):
        service.research("anything")
