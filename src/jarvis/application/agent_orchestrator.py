"""Deterministic specialist selection for the local assistant."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """One bounded specialist persona coordinated by Jarvis."""

    name: str
    instruction: str


class AgentOrchestrator:
    """Select one specialist without giving a language model tool authority."""

    _profiles = (
        (
            frozenset(
                {
                    "code",
                    "python",
                    "java",
                    "javascript",
                    "typescript",
                    "rust",
                    "bug",
                    "api",
                    "software",
                }
            ),
            AgentProfile(
                "software engineer",
                "Act as a senior software engineer. Prefer maintainable, tested, secure code.",
            ),
        ),
        (
            frozenset({"ai", "model", "llm", "embedding", "training", "inference"}),
            AgentProfile(
                "AI engineer",
                "Act as an AI engineer. Prefer measurable local inference, evaluation, and "
                "privacy-aware model choices.",
            ),
        ),
        (
            frozenset(
                {
                    "aws",
                    "azure",
                    "gcp",
                    "cloud",
                    "docker",
                    "kubernetes",
                    "terraform",
                    "deployment",
                    "cicd",
                    "devops",
                }
            ),
            AgentProfile(
                "cloud and DevOps architect",
                "Act as a cloud architect and DevOps engineer. Compare cost, reliability, "
                "security, operations, and migration effort.",
            ),
        ),
        (
            frozenset({"research", "compare", "source", "evidence", "latest"}),
            AgentProfile(
                "research analyst",
                "Act as a research analyst. Separate facts from inference and cite "
                "supplied sources.",
            ),
        ),
        (
            frozenset({"project", "milestone", "deadline", "task", "plan"}),
            AgentProfile(
                "project manager",
                "Act as a project manager. State the objective, dependencies, risks, "
                "and next action.",
            ),
        ),
        (
            frozenset({"email", "inbox", "message", "reply", "mail"}),
            AgentProfile(
                "email assistant",
                "Act as an email assistant. Be concise, preserve intent, and never claim a "
                "message was sent unless the email tool confirms it.",
            ),
        ),
        (
            frozenset({"calendar", "meeting", "appointment", "schedule", "event"}),
            AgentProfile(
                "calendar manager",
                "Act as a calendar manager. Resolve dates carefully, surface conflicts, and "
                "state the next scheduled action.",
            ),
        ),
        (
            frozenset(
                {"document", "report", "presentation", "spreadsheet", "slides", "notes"}
            ),
            AgentProfile(
                "document specialist",
                "Act as a professional document generator. Use clear structure, accurate "
                "content, and an appropriate editable format.",
            ),
        ),
        (
            frozenset({"automation", "workflow", "repetitive", "click", "form", "script"}),
            AgentProfile(
                "automation engineer",
                "Act as an automation engineer. Prefer deterministic, reversible steps and "
                "explicit checkpoints for consequential actions.",
            ),
        ),
        (
            frozenset({"budget", "expense", "finance", "financial", "invoice", "cost"}),
            AgentProfile(
                "financial organizer",
                "Act as a financial organizer, not a fiduciary. Organize supplied facts, show "
                "calculations, and flag uncertainty or professional-advice needs.",
            ),
        ),
        (
            frozenset({"learn", "study", "explain", "practice", "quiz", "course"}),
            AgentProfile(
                "learning coach",
                "Act as a learning coach. Teach at the user's level with one clear next "
                "exercise and check understanding without over-explaining.",
            ),
        ),
        (
            frozenset({"resume", "interview", "career", "job", "cover letter"}),
            AgentProfile(
                "career coach",
                "Act as a practical career coach. Give specific, truthful, "
                "outcome-focused guidance.",
            ),
        ),
        (
            frozenset({"security", "secret", "network", "threat", "vulnerability", "system"}),
            AgentProfile(
                "systems and security advisor",
                "Act as a systems and security advisor. Minimize privilege and explain "
                "material risk.",
            ),
        ),
    )
    _default = AgentProfile(
        "executive assistant",
        "Act as a concise executive assistant. Anticipate the next useful action.",
    )

    def select(self, request: str) -> AgentProfile:
        """Return the highest-scoring specialist for the current request."""
        words = set(request.casefold().replace("-", " ").split())
        best = self._default
        best_score = 0
        for keywords, profile in self._profiles:
            score = len(words.intersection(keywords))
            if score > best_score:
                best, best_score = profile, score
        return best
