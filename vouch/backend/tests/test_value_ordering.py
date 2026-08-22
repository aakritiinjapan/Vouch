"""
Tier 2c - value invariants.

This check exists because the distributional tier has a structural blind spot, and the blind spot sits
exactly on the failure the product was pitched on: a heal that starts reading the crossed-out ORIGINAL
price instead of the sale price.

Sale and original differ by maybe 10-30%. That is not enough to move a median past
check_numeric_drift's 0.5 threshold, and check_column_swap deliberately refuses to compare two fields
whose baselines are that similar (for indistinguishable fields, "closer to the other one" is noise
rather than evidence). The first two tests here prove that blindness rather than asserting it, so if
someone later loosens a threshold and thinks this check is now redundant, the record is right here.
"""

from __future__ import annotations

import pytest

from app.guardian.checks import (
    check_column_swap,
    check_numeric_drift,
    check_value_ordering,
    profile_run,
    run_all_checks,
)
from app.guardian.verdict import FAIL, PASS, decide

DISCOUNT = 0.14  # sale price sits ~14% under list - an utterly ordinary retail discount


def _rows(sale_base: float, list_base: float) -> list[dict]:
    return [{"name": f"card {i}", "price": sale_base + i * 10, "original_price": list_base + i * 10}
            for i in range(8)]


GOOD = _rows(1200.0, 1400.0)          # price below original, as it must be
SWAPPED = _rows(1400.0, 1200.0)       # the two columns traded places


# --------------------------------------------------------------------------------------
# 1. the blind spot this check exists to cover
# --------------------------------------------------------------------------------------

def test_numeric_drift_cannot_see_a_sale_original_swap():
    """A 14% discount means the swap moves the median 14% - well inside the drift threshold."""
    results = check_numeric_drift(profile_run(GOOD), profile_run(SWAPPED))
    assert results == [], "if this ever fires, re-read whether the thresholds still make sense"


def test_column_swap_cannot_see_a_sale_original_swap():
    """And the swap check refuses the comparison, correctly: these two baselines look alike."""
    results = check_column_swap(profile_run(GOOD), profile_run(SWAPPED))
    assert results == [], "price and original_price are not distinguishable by distribution"


def test_the_invariant_catches_what_the_distributions_miss():
    """The whole justification for Tier 2c, in one assertion."""
    results = check_value_ordering(SWAPPED)
    assert [r.code for r in results] == ["VALUE_ORDER_INVERTED"]
    assert results[0].severity.value == "critical"


# --------------------------------------------------------------------------------------
# 2. end to end through the verdict
# --------------------------------------------------------------------------------------

def test_a_sale_original_swap_fails_the_whole_battery():
    verdict = decide(run_all_checks(profile_run(GOOD), SWAPPED, baseline_count=len(GOOD)))
    assert verdict.decision == FAIL
    assert verdict.primary_failure.code == "VALUE_ORDER_INVERTED"
    assert "must never exceed" in verdict.brief


def test_correctly_ordered_prices_pass_cleanly():
    verdict = decide(run_all_checks(profile_run(GOOD), GOOD, baseline_count=len(GOOD)))
    assert verdict.decision == PASS
    assert verdict.confidence == 100


def test_the_invariant_needs_no_baseline_at_all():
    """It is absolute, not comparative - so it protects the very first run, before any baseline
    exists. Nothing else in the battery can do that."""
    assert check_value_ordering(SWAPPED)
    assert check_value_ordering(GOOD) == []


# --------------------------------------------------------------------------------------
# 3. tolerance - one odd row must not hold a whole catalogue
# --------------------------------------------------------------------------------------

def test_a_single_inverted_row_is_tolerated():
    """Real listings carry the occasional price-above-list oddity. One row is not a swap."""
    rows = [dict(r) for r in GOOD]
    rows[0]["price"], rows[0]["original_price"] = rows[0]["original_price"], rows[0]["price"]
    assert check_value_ordering(rows) == []


def test_a_majority_inversion_is_a_swap():
    rows = [dict(r) for r in GOOD]
    for row in rows[:5]:          # 5 of 8 = 62%, over the 20% tolerance
        row["price"], row["original_price"] = row["original_price"], row["price"]
    assert [r.code for r in check_value_ordering(rows)] == ["VALUE_ORDER_INVERTED"]


@pytest.mark.parametrize("tolerance,expected", [(0.0, 1), (0.2, 0), (0.9, 0)])
def test_tolerance_is_configurable(tolerance, expected):
    rows = [dict(r) for r in GOOD]
    rows[0]["price"], rows[0]["original_price"] = rows[0]["original_price"], rows[0]["price"]
    assert len(check_value_ordering(rows, tolerance=tolerance)) == expected


# --------------------------------------------------------------------------------------
# 4. absent, partial and malformed data
# --------------------------------------------------------------------------------------

def test_a_field_pair_that_is_absent_is_silently_skipped():
    """Most collectors will not extract original_price at all. That is not a finding."""
    assert check_value_ordering([{"name": "x", "price": 10.0, "shipping": 2.0}]) == []


def test_equal_values_are_not_an_inversion():
    """An undiscounted item legitimately has price == original_price."""
    rows = [{"name": f"x{i}", "price": 100.0, "original_price": 100.0} for i in range(8)]
    assert check_value_ordering(rows) == []


def test_rows_missing_one_side_are_ignored_not_guessed():
    rows = [{"name": "a", "price": 100.0},
            {"name": "b", "original_price": 200.0},
            {"name": "c", "price": 300.0, "original_price": 200.0}]
    # only row c is comparable, and it is inverted -> 100% of what could be checked
    results = check_value_ordering(rows)
    assert results and results[0].evidence["rows_checked"] == 1


def test_currency_strings_are_coerced_before_comparing():
    rows = [{"name": f"x{i}", "price": "$1,400.00", "original_price": "$1,200.00"} for i in range(8)]
    assert [r.code for r in check_value_ordering(rows)] == ["VALUE_ORDER_INVERTED"]


def test_no_rows_yields_no_findings():
    assert check_value_ordering([]) == []


def test_custom_orderings_can_be_supplied():
    rows = [{"name": f"x{i}", "member_price": 90.0, "price": 80.0} for i in range(8)]
    assert check_value_ordering(rows) == [], "not a default pair, so not checked"
    results = check_value_ordering(rows, orderings=[("member_price", "price")])
    assert [r.code for r in results] == ["VALUE_ORDER_INVERTED"]


def test_the_evidence_carries_what_the_ui_needs():
    evidence = check_value_ordering(SWAPPED)[0].evidence
    assert evidence["lower"] == "price"
    assert evidence["upper"] == "original_price"
    assert evidence["inverted_rate"] == 1.0
    assert evidence["rows_checked"] == 8
    assert evidence["example_lower"] > evidence["example_upper"]
