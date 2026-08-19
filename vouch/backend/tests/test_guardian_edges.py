"""
Edge cases for the guardian that the original suite left uncovered.

test_checks.py proves the guardian catches the demo's column swap. These tests prove the two things
that matter just as much but are invisible in the demo:

  1. it does NOT cry wolf - a legitimately drifting field must not be reported as a swapped one,
     because a false CRITICAL holds a price change for no reason and costs the seller a sale;
  2. the middle of the decision range (REVIEW) and the boolean checks actually work.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.guardian.checks import (
    CheckResult,
    Severity,
    check_bool_ratio,
    check_column_swap,
    profile_run,
    run_all_checks,
)
from app.guardian.verdict import FAIL, PASS, REVIEW, decide

FIXTURES = Path(__file__).parent / "fixtures" / "sample_runs.json"


def _fixture(key: str) -> list[dict]:
    return json.loads(FIXTURES.read_text())[key]


def _baseline() -> list[dict]:
    return _fixture("baseline")


def _swapped_fields(baseline_records: list[dict], proposed_records: list[dict]) -> set[str]:
    base = profile_run(baseline_records)
    return {r.field_name for r in check_column_swap(base, profile_run(proposed_records))}


# --------------------------------------------------------------------------------------
# 1. the check must still fire on a real swap
# --------------------------------------------------------------------------------------

def test_real_swap_is_still_caught():
    """The tightened check must not have narrowed so far that it misses the actual failure."""
    assert _swapped_fields(_baseline(), _fixture("healed_swapped")) == {"price", "shipping"}


# --------------------------------------------------------------------------------------
# 2. ...and must stay quiet on fields that merely drifted
# --------------------------------------------------------------------------------------

def test_legitimate_shipping_drift_is_not_a_swap():
    """Shipping falling ~28% (a promo, a carrier change) moves it toward 'rating' in absolute terms.

    A median-only comparison would call that a swap. It is not: the distribution's shape still
    matches shipping's own baseline, so no CRITICAL may be raised.
    """
    drifted = [{**r, "shipping": round(r["shipping"] * 0.72, 2)} for r in _baseline()]
    assert _swapped_fields(_baseline(), drifted) == set()


def test_free_shipping_collapse_is_not_a_swap():
    """Every row going to free shipping is a real change worth flagging - but it is not a swap, and
    mislabelling it 'looks like rating' would put a wrong diagnosis on the held card."""
    free = [{**r, "shipping": 0.0} for r in _baseline()]
    assert _swapped_fields(_baseline(), free) == set()


def test_indistinguishable_baseline_fields_cannot_produce_a_swap_claim():
    """If two baseline fields already have near-identical distributions, 'closer to the other one'
    is noise. A swap claim between them would be unfalsifiable."""
    baseline = [{"a": 10 + i, "b": 10.5 + i} for i in range(8)]
    # 'a' now carries exactly what 'b' used to - the strongest possible swap signal...
    proposed = [{"a": 10.5 + i, "b": 10.5 + i} for i in range(8)]
    # ...but the two fields were never distinguishable, so no swap may be claimed.
    assert _swapped_fields(baseline, proposed) == set()


# --------------------------------------------------------------------------------------
# 3. scoring: one root cause costs one penalty
# --------------------------------------------------------------------------------------

def test_swap_is_charged_once_not_four_times():
    """A single price/shipping swap trips COLUMN_SWAP twice and NUMERIC_DRIFT twice. Charging all
    four costs 170 points and saturates the score at 0, which reads as a broken meter."""
    baseline = _baseline()
    verdict = decide(run_all_checks(profile_run(baseline), _fixture("healed_swapped"),
                                    baseline_count=len(baseline)))
    assert verdict.decision == FAIL
    assert verdict.confidence == 40, "one CRITICAL charged once, not four correlated findings"
    assert len(verdict.failures) == 4, "all four findings are still reported to the user"
    assert verdict.primary_failure is not None
    assert verdict.primary_failure.code == "COLUMN_SWAP"


# --------------------------------------------------------------------------------------
# 4. the REVIEW branch - previously untested entirely
# --------------------------------------------------------------------------------------

def test_single_high_severity_failure_yields_review_not_fail():
    """A HIGH finding with no CRITICAL is the 'unconfirmed source' case: hold the reprice, but do
    not claim the heal is broken."""
    results = [CheckResult(False, Severity.HIGH, "price", "NULL_SPIKE",
                           "'price' is empty on 45% of rows (was 5%).", {})]
    verdict = decide(results)
    assert verdict.decision == REVIEW
    assert verdict.confidence == 75
    assert verdict.brief.startswith("Couldn't fully confirm this source.")
    assert not verdict.confirmed, "REVIEW must never read as a confirmed source"


def test_clean_run_passes_and_is_confirmed():
    verdict = decide(run_all_checks(profile_run(_baseline()), _baseline(), baseline_count=8))
    assert verdict.decision == PASS
    assert verdict.confidence == 100
    assert verdict.confirmed
    assert verdict.primary_failure is None


# --------------------------------------------------------------------------------------
# 5. boolean fields were entirely uncovered before
# --------------------------------------------------------------------------------------

def test_in_stock_pinned_to_a_constant_is_caught():
    pinned = [{**r, "in_stock": False} for r in _baseline()]
    results = check_bool_ratio(profile_run(_baseline()), profile_run(pinned))
    assert [r.code for r in results] == ["BOOL_RATIO_SHIFT"]
    assert results[0].severity == Severity.MEDIUM


def test_small_stock_change_is_not_flagged():
    """Stock genuinely fluctuates; only a collapse toward a constant is suspicious."""
    assert check_bool_ratio(profile_run(_baseline()), profile_run(_fixture("healed_good"))) == []
