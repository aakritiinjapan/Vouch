"""
Turn a list of CheckResults into the thing the product acts on:

    - a confidence score (0-100)
    - a decision: PASS / REVIEW / FAIL
    - a plain-English risk brief (what a human sees on the held card)

This is the "confidence score + risk brief that gates an action" pattern - the single strongest
winning shape we saw across the developer hackathons. Keep the brief human, short, and specific.

A verdict is a function of TWO things, not one: what the checks found, and how much they were shown.
The second half arrives as checks.Evidence, and it is what stops a clean result from two non-random
preview rows reading identically to a clean result from a whole page. The governing rule, measured
rather than assumed (docs/research/FINDINGS.md):

    A PREVIEW CAN REJECT, BUT IT CAN NEVER CONFIRM.

Which maps straight onto the three states the product already has: a sample-derived verdict that
finds nothing wrong is `held`, never `confirmed`. Not "probably fine", not "verified" - not yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .checks import CheckResult, Evidence, Severity
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

# The ceiling a verdict computed on PARTIAL evidence cannot exceed.
#
# A preview can reject, but it can never confirm. Rejecting on partial evidence is safe - the price
# does not move and the heal costs one more page load to settle. Confirming on partial evidence is the
# measured failure documented on checks.Evidence: two non-random rows, no findings, PASS 100/100, and
# a shipping charge committed as a price.
#
# 65 is chosen to sit clear of both boundaries rather than on either. Well under the 85 a PASS needs,
# so no arithmetic path reaches confirmation; comfortably over the 60 below which a verdict reads as
# FAIL, because "we did not look at enough" is not a finding against the heal and must not be
# displayed as one. A clean preview is an open question, and 65 is what an open question looks like.
PARTIAL_EVIDENCE_CEILING = 65

# Evidence assumed when a caller hands `decide` a bare list instead of a CheckBattery. See the
# CheckBattery docstring: this is the legacy contract - hand-built result lists in tests and in
# callers that judged a complete run - and defaulting it to partial would hold every such verdict
# forever.
_UNSTATED_EVIDENCE = Evidence.unstated()


def _sorted_by_severity(failures: list[CheckResult]) -> list[CheckResult]:
    return sorted(failures, key=lambda r: _SEVERITY_ORDER.index(r.severity))


@dataclass
class Verdict:
    decision: str                 # PASS / REVIEW / FAIL
    confidence: int               # 0-100
    brief: str                    # plain-English summary for the UI
    failures: list[CheckResult] = field(default_factory=list)
    # How much was looked at to produce the three fields above. Defaults to unstated (= full) so
    # every existing construction site keeps working; `decide` always sets it properly.
    evidence: Evidence = field(default_factory=Evidence.unstated)
    # Codes that never ran, so could not have fired. Empty is the honest default for a hand-built
    # verdict: claiming a check stood down when it did not is as misleading as the reverse.
    checks_stood_down: tuple[str, ...] = ()

    @property
    def confirmed(self) -> bool:
        return self.decision == PASS

    @property
    def full_battery(self) -> bool:
        """True when every check ran AND it saw the whole population.

        Both halves are required and they fail independently. A full run still has a partial battery
        if reference prices were not supplied; a complete battery over two rows is still a preview.
        A caller asking "can I trust the silence?" needs the conjunction, so it is computed here once
        rather than left for each consumer to remember to AND together.
        """
        return not self.checks_stood_down and self.evidence.is_full

    @property
    def primary_failure(self) -> Optional[CheckResult]:
        """The most severe failure - what the held card headlines and what the re-prompt targets.

        Exposed here so callers (service.py, orchestrator.py) never re-implement the severity sort.
        """
        if not self.failures:
            return None
        return min(self.failures, key=lambda r: _SEVERITY_ORDER.index(r.severity))


def _swap_field(r: CheckResult) -> str:
    """Which field a COLUMN_SWAP result is about. One definition, used by both halves of _swap_pairs,
    so a paired and an unpaired result can never disagree about what they are naming."""
    return r.evidence.get("field", r.field_name)


def _swap_pairs(failures: list[CheckResult]) -> tuple[set[frozenset[str]], int]:
    """Group COLUMN_SWAP results into the unordered field-pairs they implicate.

    check_column_swap reports a swap from BOTH sides - once as "price looks like shipping" and once
    as "shipping looks like price" - so two results describe one swap. Returns (pairs, unpaired),
    where `unpaired` counts swap results whose evidence lacks a counterpart field and so cannot be
    collapsed; those are still charged individually rather than silently going free.

    FIX, found while auditing the scoring: `unpaired` used to double-charge. A swap result carrying
    no `looks_like` was counted as its own root cause even when the SAME field already appeared in a
    pair - so one price/shipping swap reported as "price -> shipping" plus a bare "shipping" cost
    120 points for one fault. That is not merely a wrong number: it is the failure mode the pairing
    exists to prevent, arriving through the branch meant to be its safety net. An unpaired result is
    now only charged when no pair already implicates its field. A result naming a field nobody else
    named is still a distinct claim and is still charged in full.
    """
    pairs: set[frozenset[str]] = set()
    loose: list[str] = []
    for r in failures:
        if r.code != "COLUMN_SWAP":
            continue
        other = r.evidence.get("looks_like")
        if other:
            pairs.add(frozenset((_swap_field(r), other)))
        else:
            loose.append(_swap_field(r))

    # set(loose) as well as the pair subtraction: two bare results naming the same field are two
    # reports of one field being implicated, not two faults.
    already_charged = {name for pair in pairs for name in pair}
    unpaired = len(set(loose) - already_charged)
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


def decide(results: list[CheckResult], *, evidence: Optional[Evidence] = None) -> Verdict:
    """Roll a battery of check results into the decision the product acts on.

    `results` is normally the CheckBattery returned by run_all_checks, which carries its own
    Evidence; pass `evidence` explicitly only to override that or to describe a hand-built list.

    THE RULE THIS FUNCTION ENFORCES: a preview can reject, but it can never confirm.

    Findings are scored the same either way - a swap detected in two rows is a swap, and rejecting
    early is free. What partial evidence cannot do is earn a PASS, because "the checks found nothing"
    is only reassuring in proportion to what they were shown. On Bright Data's gate they are shown
    the first two tiles of thirty, and the measured consequence of treating that as confirmation was
    a shipping charge committed as a price at 100/100 (see checks.Evidence).

    So a partial verdict is capped at PARTIAL_EVIDENCE_CEILING and floored at REVIEW. Note the two
    guards are deliberately redundant: the cap keeps the NUMBER honest, and the explicit REVIEW
    branch keeps the DECISION correct even if someone later moves the ceiling. Neither is inferred
    from the other, because this is the property the whole module exists to hold.
    """
    failures = [r for r in results if not r.passed]
    if evidence is None:
        evidence = getattr(results, "evidence", None) or _UNSTATED_EVIDENCE
    confidence = _score(failures)
    if evidence.is_partial:
        confidence = min(confidence, PARTIAL_EVIDENCE_CEILING)

    has_critical = any(r.severity == Severity.CRITICAL for r in failures)
    has_high = any(r.severity == Severity.HIGH for r in failures)

    if has_critical or confidence < 60:
        decision = FAIL
    elif has_high or confidence < 85 or evidence.is_partial:
        decision = REVIEW
    else:
        decision = PASS

    return Verdict(decision=decision, confidence=confidence,
                   brief=_brief(decision, failures, evidence), failures=failures,
                   evidence=evidence, checks_stood_down=getattr(results, "stood_down", ()))


# What a clean partial verdict says instead of "Heal verified". The old text was not merely
# over-confident, it was false: it was produced by two rows that had been chosen for us, about a
# heal that was in fact reading the delivery charge. A brief that cannot be confirmed has to say what
# is missing and what would supply it, or the operator has no way to act on the hold.
_PARTIAL_CLEAN_BRIEF = (
    "Not enough evidence to confirm this heal. Nothing was wrong in the {seen} that were checked, "
    "but a preview is the first rows of a page rather than a sample drawn from it, and a swapped "
    "column can sit invisibly inside one that small. Run the healed template over the full page to "
    "settle it."
)


def _brief(decision: str, failures: list[CheckResult], evidence: Evidence) -> str:
    if not failures:
        if evidence.rows_judged == 0:
            # No rows and no findings means every check declined for want of input, which is the one
            # case where "nothing was wrong" would be actively misleading rather than merely thin.
            return ("Nothing to verify - the heal returned no rows, so there is no evidence either "
                    "way. Run the healed template over the full page.")
        if evidence.is_partial:
            return _PARTIAL_CLEAN_BRIEF.format(seen=evidence.describe())
        return "Heal verified - data still means what it should. Safe to commit."
    # lead with the most severe finding, in the user's language
    lead = _sorted_by_severity(failures)[0].message
    if decision == FAIL:
        # A rejection stands on its own evidence. It needed only one row to be true, so qualifying it
        # with how few rows there were would read as an excuse for a finding we are certain of.
        return f"Rejected this heal. {lead}"
    if decision == REVIEW:
        if evidence.is_partial:
            return (f"Couldn't confirm this heal - only {evidence.describe()} were checked, and a "
                    f"preview cannot settle it either way. {lead}")
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

      The judge may NEVER relax a PARTIAL-EVIDENCE verdict, for the same reason and a stronger one.
      It read the same two rows the checks read, so it cannot supply the evidence that is missing -
      and a model reporting "these look like prices" about two rows of shipping charges is exactly
      what the measured failure looks like from the inside. This is the one door through which a
      preview could otherwise reach PASS, so it is closed explicitly rather than left to arithmetic.
      Escalation to FAIL is untouched: a preview may always reject.

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
                       failures=verdict.failures, evidence=verdict.evidence)

    if (score >= CONFIRM_THRESHOLD and not _has_completeness_failure(verdict)
            and not verdict.evidence.is_partial):
        confidence = min(100, verdict.confidence + _JUDGE_CONFIRM_BONUS)
        if confidence >= 85:
            return Verdict(decision=PASS, confidence=confidence,
                           brief="Heal verified - the values still mean what the fields say. "
                                 "Safe to commit.",
                           failures=verdict.failures, evidence=verdict.evidence)
        return Verdict(decision=REVIEW, confidence=confidence, brief=verdict.brief,
                       failures=verdict.failures, evidence=verdict.evidence)

    return verdict


def _has_completeness_failure(verdict: Verdict) -> bool:
    return any(r.code in _COMPLETENESS_CODES for r in verdict.failures)
