"""
The cycle, end to end, with no database.

These run against unsaved Product/Baseline instances - which is the point of keeping orchestrator.py
free of Session and commit. If these tests ever need a database, the purity split has been broken.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import orchestrator
from app.guardian.checks import profile_run
from app.guardian.verdict import FAIL, PASS, REVIEW
from app.models import Baseline, Product
from app.orchestrator import run_cycle_for_product
from app.scraper import brightdata

FIXTURES = Path(__file__).parent / "fixtures" / "sample_runs.json"


def _fixture(key: str) -> list[dict]:
    return json.loads(FIXTURES.read_text())[key]


@pytest.fixture
def product() -> Product:
    # cost/floor chosen to match the demo SKU: floor = 1050 * 1.08 = 1134.00
    return Product(id=1, sku="GPU-5080-MSI", name="MSI RTX 5080 Gaming Trio",
                   my_price=1299.98, cost=1050.00, floor_margin=0.08,
                   competitor_url="https://example.com/newegg-mirror/rtx-5080-msi",
                   collector_id="c_mock_newegg_gpu")


@pytest.fixture
def baseline() -> Baseline:
    rows = _fixture("baseline")
    profiles = {name: prof.to_dict() for name, prof in profile_run(rows).items()}
    return Baseline(id=1, collector_id="c_mock_newegg_gpu", record_count=len(rows),
                    field_profiles=profiles)


@pytest.fixture
def gate_calls(monkeypatch) -> dict:
    """Count trips through the approval gate so the loop's invariants are actually asserted."""
    calls = {"approve": 0, "reject": 0}
    monkeypatch.setattr(brightdata, "approve_heal",
                        lambda cid: calls.__setitem__("approve", calls["approve"] + 1))
    monkeypatch.setattr(brightdata, "reject_heal",
                        lambda cid: calls.__setitem__("reject", calls["reject"] + 1))
    return calls


# --------------------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------------------

def test_healthy_run_does_not_heal(product, baseline, gate_calls):
    outcome = run_cycle_for_product(product, baseline)

    assert not outcome.healed, "a healthy run must never touch the heal loop"
    assert outcome.trigger_reason is None
    assert outcome.verdict is None
    assert outcome.source_confirmed
    assert outcome.competitor_price == 1299.99
    assert outcome.proposal.status == "pending"
    assert outcome.counterfactual is None
    assert gate_calls == {"approve": 0, "reject": 0}


def test_degraded_run_triggers_a_heal_with_a_measured_reason(product, baseline, gate_calls):
    """The trigger reason must be a fact the checks measured, not a sentence we typed."""
    outcome = run_cycle_for_product(product, baseline, simulate_run="run_degraded")

    assert outcome.healed
    assert "empty on 75% of rows" in outcome.trigger_reason
    assert outcome.verdict.decision == PASS, "the default mock heal is the good one"
    assert outcome.source_confirmed
    assert gate_calls == {"approve": 1, "reject": 0}


# --------------------------------------------------------------------------------------
# the guardian catching a bad heal
# --------------------------------------------------------------------------------------

def test_swapped_heal_is_rejected_and_the_reprice_is_held(product, baseline, gate_calls):
    outcome = run_cycle_for_product(product, baseline, simulate_heal=["healed_swapped",
                                                                     "healed_swapped"])

    assert not outcome.source_confirmed
    assert outcome.verdict.decision == FAIL
    assert outcome.verdict.confidence == 40
    assert outcome.competitor_price is None, "an unconfirmed source must not yield a price"
    assert outcome.proposal.status == "held"
    assert outcome.proposal.proposed_price == outcome.proposal.current_price, \
        "a held proposal must never move the price"
    assert gate_calls["approve"] == 0, "a rejected heal must never be committed"


def test_retry_cap_holds_when_every_attempt_fails(product, baseline, gate_calls):
    outcome = run_cycle_for_product(product, baseline, simulate_heal=["healed_swapped",
                                                                     "healed_swapped"])

    assert len(outcome.heal_attempts) == orchestrator.MAX_HEAL_ATTEMPTS == 2
    assert not any(a.committed for a in outcome.heal_attempts)
    assert gate_calls == {"approve": 0, "reject": 2}, "one reject per failed attempt, no open gate"


# --------------------------------------------------------------------------------------
# the resume beat: the guardian's diagnosis writes the next prompt
# --------------------------------------------------------------------------------------

def test_reprompt_recovers_and_clears_the_hold(product, baseline, gate_calls):
    """A scalar hint means 'fail once, then the sharpened prompt works' - the demo's 3:30 beat."""
    outcome = run_cycle_for_product(product, baseline, simulate_run="run_degraded",
                                    simulate_heal="healed_swapped")

    assert len(outcome.heal_attempts) == 2
    first, second = outcome.heal_attempts
    assert first.verdict.decision == FAIL and not first.committed
    assert second.verdict.decision == PASS and second.committed
    assert outcome.source_confirmed, "the hold clears once a heal is verified"
    assert outcome.proposal.status == "pending"
    assert outcome.competitor_price == 1289.99, "priced off the healed rows, not the baseline"
    assert gate_calls == {"approve": 1, "reject": 1}


def test_the_sharpened_prompt_names_the_actual_diagnosis(product, baseline):
    outcome = run_cycle_for_product(product, baseline, simulate_heal="healed_swapped")

    first, second = outcome.heal_attempts
    assert second.prompt != first.prompt, "attempt 2 must not resend the prompt that just failed"
    assert "rejected by validation" in second.prompt
    assert "SHIPPING" in second.prompt, "it must name the column the heal actually grabbed"
    assert "price" in second.prompt


def test_resharpen_never_raises_on_an_unknown_check_code(product):
    """Dict dispatch with a fallback: an unrecognised code degrades to the brief, never a KeyError."""
    from app.guardian.checks import CheckResult, Severity
    from app.guardian.verdict import decide

    verdict = decide([CheckResult(False, Severity.HIGH, "price", "SOME_FUTURE_CHECK",
                                  "Something new went wrong.", {})])
    prompt = orchestrator._resharpen_prompt(product, verdict)
    assert "Something new went wrong." in prompt
    assert verdict.decision == REVIEW


# --------------------------------------------------------------------------------------
# the counterfactual
# --------------------------------------------------------------------------------------

def test_counterfactual_reports_the_floor_clamped_price_not_the_raw_one(product, baseline):
    """The demo's 2:45 beat. Our engine would clamp to the floor, so the honest counterfactual is
    $1,134.00 - and the $19.98 a floor-less repricer would have set is the separate, worse number."""
    outcome = run_cycle_for_product(product, baseline, simulate_heal=["healed_swapped",
                                                                     "healed_swapped"])
    cf = outcome.counterfactual

    assert cf is not None
    assert cf["competitor_price"] == 19.99, "the number the rejected heal actually read"
    assert cf["applied_price"] == 1134.00, "our floor rule clamps it"
    assert cf["naive_price"] == 19.98, "a repricer with no floor rule would follow it down"
    assert cf["floor_price"] == 1134.00
    assert cf["profit_per_unit_now"] == 249.98
    assert cf["profit_per_unit_applied"] == 84.00
    assert cf["profit_delta_vs_now"] == -165.98, "the hero figure on the counterfactual panel"
    assert cf["margin_pct_naive"] < -50, "the floor-less catastrophe, as a ratio"
    assert cf["source"] == "rejected_heal_attempt_2"


def test_no_counterfactual_when_the_source_was_never_in_doubt(product, baseline):
    assert run_cycle_for_product(product, baseline).counterfactual is None


# --------------------------------------------------------------------------------------
# the simulate-hint helper
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("hint,attempt,expected", [
    (None, 1, None),
    ("healed_swapped", 1, "healed_swapped"),
    ("healed_swapped", 2, "healed_good"),          # scalar => the sharper prompt worked
    (["healed_swapped", "healed_swapped"], 2, "healed_swapped"),
    (["healed_swapped"], 5, "healed_swapped"),     # short sequence clamps to its last entry
])
def test_simulate_for_attempt(hint, attempt, expected):
    assert orchestrator._simulate_for_attempt(hint, attempt) == expected


# --------------------------------------------------------------------------------------
# the two directions of harm
# --------------------------------------------------------------------------------------

def test_a_shipping_swap_harms_margin(product, baseline):
    """Reading the shipping cost pushes our price DOWN: less margin on every unit sold."""
    outcome = run_cycle_for_product(product, baseline,
                                    simulate_heal=["healed_swapped", "healed_swapped"])
    cf = outcome.counterfactual

    assert cf["harm"] == "margin"
    assert cf["profit_delta_vs_now"] < 0
    assert "giving up" in cf["harm_summary"]


def test_an_original_price_swap_harms_competitiveness_not_margin(product, baseline):
    """Reading the crossed-out original pushes our price UP. Per-unit profit RISES, so calling this a
    margin loss would be wrong - the harm is that we price ourselves out of the sale."""
    outcome = run_cycle_for_product(
        product, baseline,
        simulate_heal=["healed_swapped_original", "healed_swapped_original"])
    cf = outcome.counterfactual

    assert cf["harm"] == "competitiveness"
    assert cf["profit_delta_vs_now"] > 0, "the price went UP"
    assert cf["margin_pct_applied"] > cf["margin_pct_now"], "per-unit margin improves - and yet"
    assert "out of the sale" in cf["harm_summary"]


def test_the_ordering_invariant_is_what_catches_the_subtle_swap(product, baseline):
    """No distributional check can see a 14% shift; only the invariant can."""
    outcome = run_cycle_for_product(
        product, baseline,
        simulate_heal=["healed_swapped_original", "healed_swapped_original"])

    assert outcome.verdict.decision == FAIL
    assert outcome.verdict.primary_failure.code == "VALUE_ORDER_INVERTED"
    codes = {f.code for f in outcome.verdict.failures}
    assert codes == {"VALUE_ORDER_INVERTED"}, \
        f"the distributional checks stayed silent, as expected; got {codes}"


def test_the_reprompt_names_the_crossed_out_price(product, baseline):
    outcome = run_cycle_for_product(product, baseline, simulate_heal="healed_swapped_original")
    second = outcome.heal_attempts[1].prompt

    assert "ORIGINAL PRICE" in second
    assert "impossible for a sale price" in second
    assert "struck-through" in second
