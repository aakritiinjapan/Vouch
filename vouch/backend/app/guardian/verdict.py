"""
Turn a list of CheckResults into the thing the product acts on:

    - a confidence score (0–100)
    - a decision: PASS / REVIEW / FAIL
    - a plain-English risk brief (what a human sees on the held card)

This is the "confidence score + risk brief that gates an action" pattern — the single strongest
winning shape we saw across the developer hackathons. Keep the brief human, short, and specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .checks import CheckResult, Severity

# how many confidence points each failed check costs
_PENALTY = {
    Severity.CRITICAL: 60,
    Severity.HIGH: 25,
    Severity.MEDIUM: 10,
    Severity.LOW: 3,
}

PASS = "pass"
REVIEW = "review"
FAIL = "fail"


@dataclass
class Verdict:
    decision: str                 # PASS / REVIEW / FAIL
    confidence: int               # 0–100
    brief: str                    # plain-English summary for the UI
    failures: list[CheckResult] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return self.decision == PASS


def decide(results: list[CheckResult]) -> Verdict:
    failures = [r for r in results if not r.passed]
    confidence = 100 - sum(_PENALTY[r.severity] for r in failures)
    confidence = max(0, min(100, confidence))

    has_critical = any(r.severity == Severity.CRITICAL for r in failures)
    has_high = any(r.severity == Severity.HIGH for r in failures)

    if has_critical or confidence < 60:
        decision = FAIL
    elif has_high or confidence < 85:
        decision = REVIEW
    else:
        decision = PASS

    return Verdict(decision=decision, confidence=confidence,
                   brief=_brief(decision, failures), failures=failures)


def _brief(decision: str, failures: list[CheckResult]) -> str:
    if not failures:
        return "Heal verified — data still means what it should. Safe to commit."
    # lead with the most severe finding, in the user's language
    order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
    failures = sorted(failures, key=lambda r: order.index(r.severity))
    lead = failures[0].message
    if decision == FAIL:
        return f"Rejected this heal. {lead}"
    if decision == REVIEW:
        return f"Couldn't fully confirm this source. {lead}"
    return lead
