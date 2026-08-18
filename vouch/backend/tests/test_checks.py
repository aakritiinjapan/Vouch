"""
The central claim of the project, as a test:

    a self-heal that silently swaps price and shipping must be REJECTED,
    a correct self-heal must PASS.

If these pass, the guardian's differentiated core works — before any Bright Data or UI code exists.
Run:  pytest -q
"""

import json
from pathlib import Path

from app.guardian.checks import profile_run, run_all_checks
from app.guardian.verdict import decide, PASS, FAIL

FIXTURES = Path(__file__).parent / "fixtures" / "sample_runs.json"


def _load():
    data = json.loads(FIXTURES.read_text())
    return data["baseline"], data["healed_good"], data["healed_swapped"]


def _verdict_for(baseline_records, proposed_records):
    baseline_profiles = profile_run(baseline_records)
    results = run_all_checks(baseline_profiles, proposed_records, baseline_count=len(baseline_records))
    return decide(results)


def test_good_heal_passes():
    baseline, good, _ = _load()
    verdict = _verdict_for(baseline, good)
    assert verdict.decision == PASS, verdict.brief
    assert verdict.confidence >= 85


def test_swapped_heal_is_rejected():
    baseline, _, swapped = _load()
    verdict = _verdict_for(baseline, swapped)
    assert verdict.decision == FAIL, f"expected FAIL, got {verdict.decision} ({verdict.brief})"
    assert verdict.confidence < 60


def test_swap_is_specifically_identified():
    """It's not enough to fail — the brief must name the swap, so the user understands the hold."""
    baseline, _, swapped = _load()
    verdict = _verdict_for(baseline, swapped)
    codes = {f.code for f in verdict.failures}
    assert "COLUMN_SWAP" in codes, f"column swap not detected; codes were {codes}"
    assert "price" in verdict.brief.lower()


def test_profiles_are_serializable():
    """Baseline profiles get stored as JSON on the Baseline row — make sure they round-trip."""
    baseline, _, _ = _load()
    profiles = profile_run(baseline)
    as_dict = {k: v.to_dict() for k, v in profiles.items()}
    assert json.loads(json.dumps(as_dict))  # no exception = serializable
