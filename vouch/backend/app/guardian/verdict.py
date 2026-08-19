"""
Turn a list of CheckResults into the thing the product acts on:

    - a confidence score (0-100)
    - a decision: PASS / REVIEW / FAIL
    - a plain-English risk brief (what a human sees on the held card)

This is the "confidence score + risk brief that gates an action" pattern - the single strongest
winning shape we saw across the developer hackathons. Keep the brief human, short, and specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .checks import CheckResult, Severity
from .judge import CONFIRM_THRESHOLD, REJECT_THRESHOLD

# how many confidence points each failed check costs
_PENALTY = {
    Severity.CRITICAL: 60,
    Severity.HIGH: 25,
    Severity.MEDIUM: 10,
    Severity.LOW: 3,
}

# most-severe first; used for both scoring order and which failure leads the brief
_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]

# Checks that fire as a downstream CONSEQUENCE of a column swap rather than as independent
# evidence of a second problem. If 'price' and 'shipping' trade places, their medians necessarily
# move too - that is the same root cause, not an extra one.
_SWAP_CONSEQUENCE_CODES = {"NUMERIC_DRIFT", "NULL_SPIKE"}

PASS = "pass"
REVIEW = "review"
FAIL = "fail"


def _sorted_by_severity(failures: list[CheckResult]) -> list[CheckResult]:
    return sorted(failures, key=lambda r: _SEVERITY_ORDER.index(r.severity))


@dataclass
class Verdict:
    decision: str                 # PASS / REVIEW / FAIL
    confidence: int               # 0-100
    brief: str                    # plain-English summary for the UI
    failures: list[CheckResult] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return self.decision == PASS

    @property
    def primary_failure(self) -> Optional[CheckResult]:
        """The most severe failure - what the held card headlines and what the re-prompt targets.

        Exposed here so callers (service.py, orchestrator.py) never re-implement the severity sort.
        """
        if not self.failures:
            return None
        return min(self.failures, key=lambda r: _SEVERITY_ORDER.index(r.severity))


def _swap_pairs(failures: list[CheckResult]) -> tuple[set[frozenset[str]], int]:
    """Group COLUMN_SWAP results into the unordered field-pairs they implicate.

    check_column_swap reports a swap from BOTH sides - once as "price looks like shipping" and once
    as "shipping looks like price" - so two results describe one swap. Returns (pairs, unpaired),
    where `unpaired` counts swap results whose evidence lacks a counterpart field and so cannot be
    collapsed; those are still charged individually rather than silently going free.
    """
    pairs: set[frozenset[str]] = set()
    unpaired = 0
    for r in failures:
        if r.code != "COLUMN_SWAP":
            continue
        other = r.evidence.get("looks_like")
        if other:
            pairs.add(frozenset((r.evidence.get("field", r.field_name), other)))
        else:
            unpaired += 1
    return pairs, unpaired


def _score(failures: list[CheckResult]) -> int:
    """Confidence = 100 minus one penalty per ROOT CAUSE.

    A single price/shipping swap trips four checks: COLUMN_SWAP on both fields plus NUMERIC_DRIFT
    on both. Charging all four costs 170 points and saturates the score at 0, which reads as a
    broken meter rather than as calibrated judgment. Every failure is still reported in
    Verdict.failures - the collapsing here affects SCORING only.
    """
    pairs, unpaired = _swap_pairs(failures)
    swapped_fields = {name for pair in pairs for name in pair}

    penalty = (len(pairs) + unpaired) * _PENALTY[Severity.CRITICAL]
    for r in failures:
        if r.code == "COLUMN_SWAP":
            continue                                      # already charged, once per pair
        if r.code in _SWAP_CONSEQUENCE_CODES and r.field_name in swapped_fields:
            continue                                      # same root cause as the swap
        penalty += _PENALTY[r.severity]

    return max(0, min(100, 100 - penalty))


def decide(results: list[CheckResult]) -> Verdict:
    failures = [r for r in results if not r.passed]
    confidence = _score(failures)

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
        return "Heal verified - data still means what it should. Safe to commit."
    # lead with the most severe finding, in the user's language
    lead = _sorted_by_severity(failures)[0].message
    if decision == FAIL:
        return f"Rejected this heal. {lead}"
    if decision == REVIEW:
        return f"Couldn't fully confirm this source. {lead}"
    return lead
# --------------------------------------------------------------------------------------
# Tier 3 - folding the semantic judge into a verdict
# --------------------------------------------------------------------------------------

# Checks that report data being ABSENT rather than wrong. A judge that looks at the values which are
# present cannot vouch for the ones that are missing, so it is never allowed to clear these.
_COMPLETENESS_CODES = {"NULL_SPIKE", "FIELD_MISSING", "ROW_COUNT_SHIFT"}

_JUDGE_CONFIRM_BONUS = 20
_JUDGE_REJECT_PENALTY = 30


def apply_judge(verdict: Verdict, judge_result) -> Verdict:
    """Let the semantic backstop move an ambiguous verdict - in either direction.

    Only meaningful on REVIEW. The rules, and why:

      The judge may ESCALATE to FAIL. This is the case Tier 3 exists for: values whose distribution
      looked acceptable but whose meaning is wrong. The statistics cannot see it; a reader can.

      The judge may RELAX to PASS only when every failing check was distributional. If the doubt came
      from missing data (a null spike, a dropped field, a row-count collapse) the judge has nothing to
      say about it - it read the rows that ARE there. Letting it clear a completeness failure would be
      the model vouching for data it never saw.

    A judge that was not consulted, or could not be reached, returns the verdict untouched.
    """
    if verdict.decision != REVIEW:
        return verdict
    if not getattr(judge_result, "consulted", False):
        return verdict

    worst = judge_result.worst
    if worst is None:
        return verdict
    worst_field, score = worst
    reason = (getattr(judge_result, "reasons", {}) or {}).get(worst_field, "")

    if score < REJECT_THRESHOLD:
        confidence = max(0, verdict.confidence - _JUDGE_REJECT_PENALTY)
        brief = (f"Rejected this heal. The values in '{worst_field}' do not mean what the field "
                 f"says: {reason}" if reason else
                 f"Rejected this heal. The values in '{worst_field}' do not mean what the field says.")
        return Verdict(decision=FAIL, confidence=confidence, brief=brief,
                       failures=verdict.failures)

    if score >= CONFIRM_THRESHOLD and not _has_completeness_failure(verdict):
        confidence = min(100, verdict.confidence + _JUDGE_CONFIRM_BONUS)
        if confidence >= 85:
            return Verdict(decision=PASS, confidence=confidence,
                           brief="Heal verified - the values still mean what the fields say. "
                                 "Safe to commit.",
                           failures=verdict.failures)
        return Verdict(decision=REVIEW, confidence=confidence, brief=verdict.brief,
                       failures=verdict.failures)

    return verdict


def _has_completeness_failure(verdict: Verdict) -> bool:
    return any(r.code in _COMPLETENESS_CODES for r in verdict.failures)
