"""
Judging a PREVIEW SAMPLE rather than a full run.

Bright Data's approval gate does not hand you the whole healed dataset - it hands you
`preview_result`, a sample. Measured against the live Newegg collector: **1 row** against a 96-row
baseline. That is the data the guardian has to gate on, so it has to reason correctly about it.

Left unhandled, the volume-dependent checks measure the preview size instead of the heal and report
"Row count changed from 96 to 1" - safe, because it fails closed, but the wrong diagnosis. Nobody
should have to explain that on stage.

The two halves of this file are equally important:
  - the volume checks stand down on a sample (no false findings);
  - every check that CAN work on one row still does (no lost detection).
"""

from __future__ import annotations

import pytest

from app.guardian.checks import MIN_ROWS_FOR_DISTRIBUTION, profile_run, run_all_checks
from app.guardian.verdict import FAIL, PARTIAL_EVIDENCE_CEILING, PASS, REVIEW, decide

# Shaped like the real collector's output: 96 cards, wide price spread, shipping almost always free.
BASELINE = [
    {"name": f"GeForce Card Model {i:02d}", "product_page_url": f"https://example.com/p/{i}",
     "price": 200.0 + i * 60, "shipping": 0.0 if i % 12 else 19.99,
     "rating": 4.0, "in_stock": i % 8 != 0}
    for i in range(96)
]

# One legitimately-extracted row, mid-range - exactly what the live gate returned.
GOOD_PREVIEW = [{"name": "SAPPHIRE PULSE Radeon RX 9060 XT 16GB",
                 "product_page_url": "https://example.com/p/sapphire",
                 "price": 519.99, "shipping": 0.0, "rating": 4.0, "in_stock": True}]


def _verdict(rows: list[dict], *, is_sample: bool):
    return decide(run_all_checks(profile_run(BASELINE), rows,
                                 baseline_count=len(BASELINE), is_sample=is_sample))


# --------------------------------------------------------------------------------------
# 1. no false findings from the sample size
# --------------------------------------------------------------------------------------

def test_a_one_row_preview_of_a_good_heal_is_held_not_confirmed():
    """The real case, and the one this file originally got wrong.

    This test used to assert PASS 100/100, on the reasoning that the heal extracted a valid price and
    the guardian should say so. The first half is right and is still asserted below: the sample size
    must not manufacture findings, so `failures` stays empty.

    The second half was wrong, and docs/research/FINDINGS.md is the measurement that proves it. A
    heal that put the delivery charge in `price` produced an equally empty failure list on the gate's
    preview and scored the same 100/100 - because the checks that catch a swap are distributional and
    a preview switches them off. If a good heal and a broken one are indistinguishable at the gate,
    then a clean preview is not evidence of a good heal, and confirming on it is not a judgement.

    So the correct answer is REVIEW: nothing objected, but nothing was in a position to. Confirming
    requires a full run, which costs one more page load.
    """
    verdict = _verdict(GOOD_PREVIEW, is_sample=True)

    assert verdict.failures == [], "sample size must not invent findings"
    assert verdict.decision == REVIEW
    assert verdict.confirmed is False
    assert verdict.confidence <= PARTIAL_EVIDENCE_CEILING
    assert verdict.full_battery is False


def test_without_the_sample_flag_the_same_preview_is_misdiagnosed():
    """Documents the bug this flag fixes, so the reason for it cannot be lost in a refactor."""
    verdict = _verdict(GOOD_PREVIEW, is_sample=False)

    codes = {f.code for f in verdict.failures}
    assert verdict.decision == REVIEW
    assert "ROW_COUNT_SHIFT" in codes, "it complains about the preview size"
    assert "CARDINALITY_COLLAPSE" in codes, "and about one row having one distinct name"


@pytest.mark.parametrize("code", ["ROW_COUNT_SHIFT", "CARDINALITY_COLLAPSE"])
def test_volume_checks_stand_down_on_a_sample(code):
    assert code not in {f.code for f in _verdict(GOOD_PREVIEW, is_sample=True).failures}


def test_numeric_drift_stands_down_when_there_are_too_few_rows():
    """A cheap card in a one-row preview would otherwise read as a 60% price collapse."""
    cheap = [{**GOOD_PREVIEW[0], "price": 200.0}]
    assert "NUMERIC_DRIFT" not in {f.code for f in _verdict(cheap, is_sample=True).failures}


def test_numeric_drift_still_applies_once_there_are_enough_rows():
    """Standing down is about sample size, not about samples being exempt from scrutiny."""
    many = [{**GOOD_PREVIEW[0], "price": 60.0} for _ in range(MIN_ROWS_FOR_DISTRIBUTION)]
    assert "NUMERIC_DRIFT" in {f.code for f in _verdict(many, is_sample=True).failures}


# --------------------------------------------------------------------------------------
# 2. no lost detection - the half that actually matters
# --------------------------------------------------------------------------------------

def test_a_shipping_swap_is_still_caught_from_one_row():
    """COLUMN_SWAP asks which distribution a value sits ON, not how it is spread - so one row is
    enough. This is the demo's headline failure, and it must survive the sample path."""
    swapped = [{**GOOD_PREVIEW[0], "price": 0.0, "shipping": 519.99}]
    verdict = _verdict(swapped, is_sample=True)

    assert verdict.decision == FAIL
    assert verdict.primary_failure.code == "COLUMN_SWAP"


def test_a_dropped_field_is_still_caught_from_one_row():
    without_price = [{k: v for k, v in GOOD_PREVIEW[0].items() if k != "price"}]
    verdict = _verdict(without_price, is_sample=True)

    assert verdict.decision == FAIL
    assert verdict.primary_failure.code == "FIELD_MISSING"


def test_a_null_price_is_still_caught_from_one_row():
    nulled = [{**GOOD_PREVIEW[0], "price": None}]
    verdict = _verdict(nulled, is_sample=True)

    assert verdict.decision == REVIEW
    assert "NULL_SPIKE" in {f.code for f in verdict.failures}


def test_a_crossed_out_original_is_still_caught_from_one_row():
    """The row-wise invariant needs no volume at all - one row is a complete test of it."""
    inverted = [{**GOOD_PREVIEW[0], "price": 592.79, "original_price": 519.99}]
    verdict = _verdict(inverted, is_sample=True)

    assert verdict.decision == FAIL
    assert verdict.primary_failure.code == "VALUE_ORDER_INVERTED"


def test_an_empty_preview_is_not_silently_accepted():
    """No rows at all means the heal produced nothing to vouch for."""
    verdict = _verdict([], is_sample=True)
    assert verdict.decision != PASS


# --------------------------------------------------------------------------------------
# 3. the flag reaches the battery from the gate
# --------------------------------------------------------------------------------------

def test_the_real_gate_marks_its_rows_as_a_sample(monkeypatch):
    import json

    from app.scraper import brightdata

    monkeypatch.setattr(brightdata.settings, "mock_mode", False)
    monkeypatch.setattr(brightdata, "_cli", lambda *a: json.dumps({
        "collector_id": "c_abc", "status": "awaiting_approval", "preview_result": GOOD_PREVIEW,
    }))

    proposal = brightdata.propose_heal("c_abc", "prompt", "https://example.com/x")
    assert proposal.is_sample is True, "preview_result is always a sample"


def test_the_mock_gate_does_not(monkeypatch):
    """The fixture stands in for a full run, so pretending it is a sample would disable checks the
    demo depends on."""
    from app.scraper import brightdata

    monkeypatch.setattr(brightdata.settings, "mock_mode", True)
    proposal = brightdata.propose_heal("c_x", "prompt", "https://example.com/x")
    assert proposal.is_sample is False
