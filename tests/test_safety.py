"""Safety policy tests."""

from __future__ import annotations

import pytest

from jarvis.core.safety import ActionPolicy, PolicyDecision, RiskLevel


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        (RiskLevel.SAFE, PolicyDecision.ALLOW),
        (RiskLevel.CONFIRM, PolicyDecision.REQUIRE_CONFIRMATION),
        (RiskLevel.FORBIDDEN, PolicyDecision.DENY),
    ],
)
def test_restrictive_policy(risk: RiskLevel, expected: PolicyDecision) -> None:
    assert ActionPolicy().evaluate(risk) is expected


def test_confirmation_can_be_disabled_without_allowing_forbidden_actions() -> None:
    policy = ActionPolicy(require_confirmation=False)

    assert policy.evaluate(RiskLevel.CONFIRM) is PolicyDecision.ALLOW
    assert policy.evaluate(RiskLevel.FORBIDDEN) is PolicyDecision.DENY
