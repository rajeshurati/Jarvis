"""Deterministic action-risk policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    """Risk assigned to a proposed assistant action."""

    SAFE = "safe"
    CONFIRM = "confirm"
    FORBIDDEN = "forbidden"


class PolicyDecision(StrEnum):
    """Outcome returned by the policy engine."""

    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    """Evaluate risk independently of any language model."""

    require_confirmation: bool = True

    def evaluate(self, risk: RiskLevel) -> PolicyDecision:
        """Map a typed risk level to an execution decision."""
        if risk is RiskLevel.FORBIDDEN:
            return PolicyDecision.DENY
        if risk is RiskLevel.CONFIRM and self.require_confirmation:
            return PolicyDecision.REQUIRE_CONFIRMATION
        return PolicyDecision.ALLOW
