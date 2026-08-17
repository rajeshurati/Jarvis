"""Deterministic policies for natural spoken turns."""

from __future__ import annotations

import re


class ConversationPolicy:
    """Prioritize the latest intent and bound every spoken response."""

    _interruption = re.compile(
        r"^(?:jarvis[\s,]+)?(?:stop talking|wait|hold on|no|actually|instead|new topic)"
        r"[\s,;:-]+(?P<intent>.+)$",
        re.IGNORECASE,
    )
    _filler = re.compile(
        r"^(?:(?:understood|certainly|of course|absolutely|sure)(?:,?\s+rajesh)?"
        r"[.,!:-]*\s*)+",
        re.IGNORECASE,
    )
    _dangling_ending = re.compile(
        r"(?:\s+|^)(?:and|or|but|with|including|which|that|for|to|of|in|on|via|like|showing)$",
        re.IGNORECASE,
    )
    _unfinished_question = re.compile(
        r"^(?:(?:what|who|where|when|why|how)\s+"
        r"(?:is|are|was|were|do|does|did|can|could|would|should)|"
        r"(?:can|could|would|will|do|did)\s+you)$",
        re.IGNORECASE,
    )

    def __init__(self, max_words: int = 28, max_sentences: int = 2) -> None:
        self._max_words = max_words
        self._max_sentences = max_sentences

    def latest_intent(self, transcript: str) -> tuple[str, bool]:
        """Remove a conversational interruption prefix and flag the topic change."""
        normalized = re.sub(r"\s+", " ", transcript).strip()
        match = self._interruption.fullmatch(normalized)
        if match is None:
            return normalized, False
        return match.group("intent").strip(), True

    def clarification_for(self, transcript: str) -> str | None:
        """Return a natural prompt when speech recognition captured only a fragment."""
        normalized = re.sub(r"[^a-zA-Z0-9' ]", "", transcript).strip()
        if self._unfinished_question.fullmatch(normalized):
            return "Please finish your question. I am listening."
        return None

    def spoken_reply(self, text: str) -> str:
        """Convert model prose into at most two short speech-friendly sentences."""
        cleaned = text.replace("\r", "\n")
        cleaned = re.sub(r"(?m)^\s*(?:#{1,6}|[-*+]|\d+[.)])\s*", "", cleaned)
        cleaned = re.sub(r"[*_`>#]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"^(?:jarvis|assistant)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = self._filler.sub("", cleaned).strip()
        if not cleaned:
            return "I do not have a useful answer yet."

        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        selected: list[str] = []
        word_count = 0
        for sentence in sentences[: self._max_sentences]:
            sentence_words = sentence.split()
            if selected and word_count + len(sentence_words) > self._max_words:
                break
            selected.append(sentence)
            word_count += len(sentence_words)
        if len(selected) > 1 and len(selected[-1].split()) <= 3:
            word_count -= len(selected[-1].split())
            selected.pop()
        response = " ".join(selected).strip()
        if word_count <= self._max_words:
            return response
        shortened = " ".join(response.split()[: self._max_words]).rstrip(",;:-")
        comma = max(shortened.rfind(","), shortened.rfind(";"))
        if comma >= 40:
            shortened = shortened[:comma].rstrip()
        while self._dangling_ending.search(shortened):
            shortened = self._dangling_ending.sub("", shortened).rstrip(",;:-")
        return f"{shortened}."
