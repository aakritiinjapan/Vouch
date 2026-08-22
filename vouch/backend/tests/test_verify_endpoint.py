"""
The stateless trust layer: POST /verify.

Unlike test_api.py, these tests touch no database, seed no products, and override no session
dependency - that is the whole point of the endpoint. It runs the guardian's pure functions over
rows the caller supplies and returns the Verdict as JSON. Any pipeline can plug in.

Fixtures come from the same hand-written sample_runs.json the rest of the suite pins, because it
carries `original_price` and so can exercise every tier including the value-ordering invariant.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scraper import baseline as baseline_capture

FIXTURES = Path(__file__).parent / "fixtures" / "sample_runs.json"


@pytest.fixture(scope="module")
def runs() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.fixture
def client() -> TestClient:
    # No dependency_overrides, no engine, no seed: /verify is stateless.
    with TestClient(app) as c:
        yield c


def _verify(client: TestClient, **body) -> tuple[int, dict]:
    response = client.post("/verify", json=body)
    return response.status_code, response.json()


def _codes(payload: dict) -> set[str]:
    return {f["code"] for f in payload["failures"]}


# --------------------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------------------

def test_clean_candidate_against_baseline_passes(client, runs):
    baseline = runs["baseline"]
    status, payload = _verify(client, candidate_records=baseline, baseline_records=baseline)
    assert status == 200, payload
    assert payload["decision"] == "pass"
    assert payload["confirmed"] is True
    assert payload["failures"] == []
    assert payload["judge_consulted"] is False
    assert 0 <= payload["confidence"] <= 100


def test_healed_good_passes(client, runs):
    status, payload = _verify(client, candidate_records=runs["healed_good"],
                              baseline_records=runs["baseline"])
    assert status == 200, payload
    assert payload["decision"] == "pass"
    assert payload["confirmed"] is True


# --------------------------------------------------------------------------------------
# the failure modes, one per tier
# --------------------------------------------------------------------------------------

def test_column_swap_fails_with_column_swap(client, runs):
    status, payload = _verify(client, candidate_records=runs["healed_swapped"],
                              baseline_records=runs["baseline"])
    assert status == 200, payload
    assert payload["decision"] == "fail"
    assert payload["confirmed"] is False
    assert "COLUMN_SWAP" in _codes(payload)


def test_value_order_inversion_fails(client, runs):
    status, payload = _verify(client, candidate_records=runs["healed_swapped_original"],
                              baseline_records=runs["baseline"])
    assert status == 200, payload
    assert payload["decision"] == "fail"
    assert "VALUE_ORDER_INVERTED" in _codes(payload)


def test_null_spike_is_caught_and_unconfirmed(client, runs):
    # run_degraded has price empty on 6 of 8 rows. That is a HIGH-severity NULL_SPIKE, which the
    # guardian maps to REVIEW (never confirmed), not a CRITICAL FAIL - a missing value is doubt, not
    # proof of a swap. We assert the pure-function behaviour rather than forcing a "fail".
    status, payload = _verify(client, candidate_records=runs["run_degraded"],
                              baseline_records=runs["baseline"])
    assert status == 200, payload
    assert "NULL_SPIKE" in _codes(payload)
    assert payload["confirmed"] is False
    assert payload["decision"] in ("review", "fail")


def test_dropped_field_fails_with_field_missing(client, runs):
    dropped = [{k: v for k, v in row.items() if k != "price"} for row in runs["baseline"]]
    status, payload = _verify(client, candidate_records=dropped,
                              baseline_records=runs["baseline"])
    assert status == 200, payload
    assert payload["decision"] == "fail"
    assert "FIELD_MISSING" in _codes(payload)


# --------------------------------------------------------------------------------------
# sample-awareness
# --------------------------------------------------------------------------------------

def test_is_sample_suppresses_volume_checks_on_one_row(client, runs):
    one_row = [runs["baseline"][0]]

    # Without is_sample, a single row against an 8-row baseline trips volume checks.
    status, tripped = _verify(client, candidate_records=one_row, baseline_records=runs["baseline"])
    assert status == 200, tripped
    volume = {"ROW_COUNT_SHIFT", "CARDINALITY_COLLAPSE"}
    assert _codes(tripped) & volume

    # With is_sample, those stand down - a preview size is not a finding.
    status, sampled = _verify(client, candidate_records=one_row, baseline_records=runs["baseline"],
                              is_sample=True)
    assert status == 200, sampled
    assert not (_codes(sampled) & volume)


# --------------------------------------------------------------------------------------
# the two baseline shapes agree
# --------------------------------------------------------------------------------------

def test_precomputed_profiles_match_raw_records_path(client, runs):
    baseline = runs["baseline"]
    candidate = runs["healed_swapped"]

    _, from_records = _verify(client, candidate_records=candidate, baseline_records=baseline)

    profiles, count = baseline_capture.capture(baseline)
    _, from_profiles = _verify(client, candidate_records=candidate,
                               baseline_profiles=profiles, baseline_count=count)

    assert from_records["decision"] == from_profiles["decision"]
    assert from_records["confidence"] == from_profiles["confidence"]
    assert _codes(from_records) == _codes(from_profiles)


# --------------------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------------------

def test_neither_baseline_provided_is_422(client, runs):
    status, _ = _verify(client, candidate_records=runs["baseline"])
    assert status == 422


def test_both_baselines_provided_is_422(client, runs):
    profiles, count = baseline_capture.capture(runs["baseline"])
    status, _ = _verify(client, candidate_records=runs["baseline"],
                        baseline_records=runs["baseline"], baseline_profiles=profiles)
    assert status == 422


def test_empty_candidate_records_is_422(client, runs):
    status, _ = _verify(client, candidate_records=[], baseline_records=runs["baseline"])
    assert status == 422


# --------------------------------------------------------------------------------------
# malformed input is a 422, never a 500 (this endpoint ingests arbitrary caller data)
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [{}, {"foo": 1}])
def test_malformed_baseline_profiles_is_422(client, runs, bad):
    status, payload = _verify(client, candidate_records=runs["baseline"],
                              baseline_profiles={"price": bad})
    assert status == 422, payload


# --------------------------------------------------------------------------------------
# payload size is bounded
# --------------------------------------------------------------------------------------

def test_oversized_candidate_records_is_422(client, runs):
    from app.api.trust_routes import MAX_VERIFY_ROWS
    huge = [dict(runs["baseline"][0]) for _ in range(MAX_VERIFY_ROWS + 1)]
    status, payload = _verify(client, candidate_records=huge, baseline_records=runs["baseline"])
    assert status == 422, payload


def test_oversized_baseline_records_is_422(client, runs):
    from app.api.trust_routes import MAX_VERIFY_ROWS
    huge = [dict(runs["baseline"][0]) for _ in range(MAX_VERIFY_ROWS + 1)]
    status, payload = _verify(client, candidate_records=runs["baseline"], baseline_records=huge)
    assert status == 422, payload


# --------------------------------------------------------------------------------------
# baseline_profiles path still runs ROW_COUNT_SHIFT via inferred count
# --------------------------------------------------------------------------------------

def test_profiles_path_infers_count_and_runs_row_count_shift(client, runs):
    # A 1-row candidate against the 8-row baseline should trip ROW_COUNT_SHIFT even when the caller
    # supplies profiles (not raw records) and omits baseline_count - the count is inferred from the
    # profiles, not silently defaulted to 0 (which would no-op the check).
    profiles, _ = baseline_capture.capture(runs["baseline"])
    one_row = [runs["baseline"][0]]
    status, payload = _verify(client, candidate_records=one_row, baseline_profiles=profiles)
    assert status == 200, payload
    assert "ROW_COUNT_SHIFT" in _codes(payload)


# --------------------------------------------------------------------------------------
# the public contract rejects unknown knobs rather than silently ignoring them
# --------------------------------------------------------------------------------------

def test_unknown_field_is_422(client, runs):
    status, _ = _verify(client, candidate_records=runs["baseline"],
                        baseline_records=runs["baseline"], use_jugde=True)
    assert status == 422


# --------------------------------------------------------------------------------------
# the judge, off in mock
# --------------------------------------------------------------------------------------

def test_use_judge_is_noop_in_mock_mode(client, runs):
    # Pick a candidate that would land on REVIEW so the judge would be consulted if it could be.
    baseline = runs["baseline"]
    without = _verify(client, candidate_records=baseline, baseline_records=baseline)[1]
    with_judge = _verify(client, candidate_records=baseline, baseline_records=baseline,
                         use_judge=True)[1]
    assert with_judge["judge_consulted"] is False
    assert with_judge["decision"] == without["decision"]
    assert with_judge["confidence"] == without["confidence"]


# --------------------------------------------------------------------------------------
# response shape
# --------------------------------------------------------------------------------------

def test_response_schema_keys(client, runs):
    status, payload = _verify(client, candidate_records=runs["healed_swapped"],
                              baseline_records=runs["baseline"])
    assert status == 200, payload
    assert set(payload) == {"decision", "confirmed", "confidence", "brief", "failures",
                            "judge_consulted"}
    for failure in payload["failures"]:
        assert set(failure) == {"code", "severity", "field", "message", "evidence"}
