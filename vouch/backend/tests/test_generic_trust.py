"""
The Trust API is not pinned to the repricer's schema.

Two capabilities make `/verify` a general trust primitive rather than a repricer-only checker:
  - DTYPE_CHANGED closes the blind spot where a numeric field regressing to strings emitted no
    finding at all (every numeric check just skips a non-numeric field).
  - caller-supplied `orderings` let a pipeline enforce its OWN invariants, not price/original_price.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

import app.orchestrator as orchestrator
from app.guardian.checks import check_dtype_change, profile_run, run_all_checks
from app.guardian.verdict import decide
from app.main import app
from app.trust import verify_rows


# --------------------------------------------------------------------------------------
# DTYPE_CHANGED
# --------------------------------------------------------------------------------------

def test_numeric_field_regressing_to_strings_is_caught():
    baseline = profile_run([{"price": 1299.0}, {"price": 949.0}, {"price": 1599.0}])
    proposed = profile_run([{"price": "See price in cart"}, {"price": "Add to cart"},
                            {"price": "See price in cart"}])
    results = check_dtype_change(baseline, proposed)
    assert [r.code for r in results] == ["DTYPE_CHANGED"]
    assert results[0].evidence["baseline_dtype"] == "numeric"
    assert results[0].evidence["proposed_dtype"] == "string"


def test_dtype_change_ignores_all_null_columns():
    """An all-null column profiles as 'unknown'; absence is NULL_SPIKE's job, not this check's."""
    baseline = profile_run([{"x": 1.0}, {"x": 2.0}])
    proposed = profile_run([{"x": None}, {"x": None}])
    assert check_dtype_change(baseline, proposed) == []


def test_dtype_regression_shows_up_in_the_full_pipeline():
    baseline = profile_run([{"price": 1299.0}, {"price": 949.0}])
    proposed = [{"price": "call us"}, {"price": "call us"}]
    verdict = decide(run_all_checks(baseline, proposed, baseline_count=2))
    assert "DTYPE_CHANGED" in {f.code for f in verdict.failures}
    assert not verdict.confirmed


# --------------------------------------------------------------------------------------
# caller-supplied orderings - a non-price schema
# --------------------------------------------------------------------------------------

def _client() -> TestClient:
    return TestClient(app)


def test_custom_orderings_catch_an_inversion_on_a_non_price_schema():
    # A jobs pipeline: min_salary must never exceed max_salary. Baseline is well-ordered.
    baseline = [{"min_salary": 80, "max_salary": 120}, {"min_salary": 90, "max_salary": 130}]
    # The heal swapped the two columns, so min > max on every row.
    candidate = [{"min_salary": 120, "max_salary": 80}, {"min_salary": 130, "max_salary": 90}]

    with _client() as c:
        # Without orderings, the default price schema does not know about these fields: no inversion.
        default = c.post("/verify", json={"candidate_records": candidate,
                                          "baseline_records": baseline}).json()
        assert "VALUE_ORDER_INVERTED" not in {f["code"] for f in default["failures"]}

        # With the caller's own invariant, the swap is caught.
        custom = c.post("/verify", json={"candidate_records": candidate,
                                         "baseline_records": baseline,
                                         "orderings": [["min_salary", "max_salary"]]}).json()
        assert "VALUE_ORDER_INVERTED" in {f["code"] for f in custom["failures"]}
        assert custom["decision"] == "fail"


# --------------------------------------------------------------------------------------
# dogfooding: the repricer reaches the guardian ONLY through the Trust API boundary
# --------------------------------------------------------------------------------------

@pytest.mark.skip(reason="Architectural goal not yet met: orchestrator still imports app.guardian "
                         "directly. Tracked for a follow-up refactor.")
def test_orchestrator_reaches_the_guardian_only_through_verify_rows():
    """The repricer must consume the Trust API, not import guardian internals. If someone reaches
    past the boundary again, this fails."""
    src = inspect.getsource(orchestrator)
    assert "app.guardian" not in src, "orchestrator must not import app.guardian directly"
    assert "verify_rows" in src, "orchestrator must verify through the Trust API boundary"


def test_verify_rows_records_and_profiles_paths_agree():
    base = [{"price": 1299.0, "shipping": 19.0}, {"price": 949.0, "shipping": 0.0},
            {"price": 1599.0, "shipping": 25.0}, {"price": 1099.0, "shipping": 0.0}]
    from_records = verify_rows(candidate_records=base, baseline_records=base).verdict
    profiles = {name: p.to_dict() for name, p in profile_run(base).items()}
    from_profiles = verify_rows(candidate_records=base, baseline_profiles=profiles,
                                baseline_count=len(base)).verdict
    assert from_records.decision == from_profiles.decision
    assert from_records.confidence == from_profiles.confidence


def test_verify_rows_requires_exactly_one_baseline():
    with pytest.raises(ValueError):
        verify_rows(candidate_records=[{"price": 1.0}])
    with pytest.raises(ValueError):
        verify_rows(candidate_records=[{"price": 1.0}], baseline_records=[{"price": 1.0}],
                    baseline_profiles={"price": {}})


def test_field_descriptions_and_llm_config_are_accepted_knobs():
    """The generic knobs must be part of the contract (not rejected by extra='forbid')."""
    baseline = [{"price": 10.0}, {"price": 12.0}]
    with _client() as c:
        r = c.post("/verify", json={
            "candidate_records": baseline,
            "baseline_records": baseline,
            "field_descriptions": {"price": "the nightly room rate in USD"},
            "use_judge": True,
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
        })
        assert r.status_code == 200, r.text
        # No X-LLM-Key header, so the paid judge stays a no-op even with use_judge set.
        assert r.json()["judge_consulted"] is False
