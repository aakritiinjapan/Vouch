"""
The demo dataset is derived from real collector output, and the app must not overclaim about it.

Two things are worth locking down:

  1. The derivation. `newegg_live` is generated from docs/sample_output.json, so its baseline has to
     stay a faithful copy of what the collector returned - if a regeneration ever starts inventing
     rows, the whole "the demo runs on real data" claim quietly stops being true.
  2. The honesty of the demo controls. That dataset carries no `original_price`, because the
     collector never captured one, so the value-ordering scenario cannot be replayed against it. The
     dashboard must not offer a control the data cannot honour.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.scraper.brightdata import _FIXTURE_DIR

LIVE = "newegg_live"
HAND_WRITTEN = "sample_runs"


def _dataset(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def use_dataset(monkeypatch):
    def _use(name: str):
        monkeypatch.setattr(settings, "demo_dataset", name)
    return _use


# --------------------------------------------------------------------------------------
# the derivation
# --------------------------------------------------------------------------------------

def test_live_baseline_matches_the_real_collector_output():
    """Every baseline row must be a row the collector actually returned, at the price it returned."""
    source = json.loads((_FIXTURE_DIR.parents[1].parent / "docs" / "sample_output.json")
                        .read_text(encoding="utf-8"))
    real = {}
    for record in source["rows"]:
        for card in record.get("graphics_cards", []):
            price = card.get("price")
            if isinstance(price, dict):
                price = price.get("value")
            if card.get("name") and price is not None:
                real[card["name"].strip()] = round(float(price), 2)

    baseline = _dataset(LIVE)["baseline"]
    assert baseline, "the live dataset has no baseline rows"
    for row in baseline:
        assert row["name"] in real, f"{row['name']!r} is not in the real collector output"
        assert row["price"] == real[row["name"]], f"price drifted from the real run for {row['name']}"


def test_live_dataset_carries_no_invented_original_price():
    """The collector did not capture original_price. Adding one to make a demo work would be a lie."""
    for key, rows in _dataset(LIVE).items():
        if key.startswith("_"):
            continue
        assert all("original_price" not in row for row in rows), (
            f"{key} carries original_price, which the live collector never returned"
        )


def test_the_swap_exchanges_real_values_in_both_directions():
    """healed_swapped must be a true exchange of two real fields, not a fabricated low number."""
    data = _dataset(LIVE)
    baseline = {row["name"]: row for row in data["baseline"]}

    for swapped in data["healed_swapped"]:
        original = baseline[swapped["name"]]
        assert swapped["price"] == original["shipping"]
        assert swapped["shipping"] == original["price"]

    # And the swap has to actually be catchable: the two distributions must not already coincide.
    prices = sorted(row["price"] for row in data["baseline"])
    assert prices[len(prices) // 2] > 100, "baseline prices are too low for the swap to be a swap"


def test_degraded_run_is_degraded_enough_to_trigger_a_heal():
    rows = _dataset(LIVE)["run_degraded"]
    missing = sum(1 for row in rows if row["price"] is None)
    assert missing / len(rows) > 0.5, "the degraded run would not trip the degradation gate"


# --------------------------------------------------------------------------------------
# the demo controls
# --------------------------------------------------------------------------------------

def test_hints_omit_the_scenario_the_live_data_cannot_replay(use_dataset):
    use_dataset(LIVE)
    with TestClient(app) as client:
        body = client.get("/demo/hints").json()

    assert body["dataset"] == LIVE
    keys = {hint["key"] for hint in body["hints"]}
    assert "healed_swapped" in keys, "the flagship scenario must be offered"
    assert "healed_swapped_original" not in keys, (
        "offered a crossed-out-price replay against data with no original_price"
    )


def test_hints_offer_value_ordering_against_the_hand_written_set(use_dataset):
    use_dataset(HAND_WRITTEN)
    with TestClient(app) as client:
        keys = {hint["key"] for hint in client.get("/demo/hints").json()["hints"]}

    assert "healed_swapped_original" in keys, (
        "the hand-written set does carry original_price, so this scenario should be available"
    )


def test_every_offered_hint_is_actually_accepted_by_the_cycle_endpoint(use_dataset):
    """A control the dashboard renders must not 422 when clicked."""
    use_dataset(LIVE)
    with TestClient(app) as client:
        hints = client.get("/demo/hints").json()["hints"]
        known = set(client.post("/cycles/run", json={"simulate_heal": "nope"}).json()
                    ["detail"]["known"])

    assert hints, "no hints offered at all"
    for hint in hints:
        assert hint["key"] in known, f"{hint['key']} is offered but rejected as unknown"
