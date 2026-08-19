"""
The API, driven the way the demo drives it.

test_service.py proves the right rows get written. This file proves the seller's actual journey works
over HTTP: routine batch approve, the break, the held card with its risk brief, the counterfactual,
the resume, and the reset that lets you rehearse it again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import session_dep
from app.main import app
from app.models import Product

FIXTURES = Path(__file__).parent / "fixtures" / "sample_runs.json"
COLLECTOR = "c_mock_newegg_gpu"

SEED = [
    dict(sku="GPU-5080-MSI", name="MSI RTX 5080 Gaming Trio", my_price=1319.00, cost=1050.00,
         floor_margin=0.08, competitor_url="https://example.com/newegg-mirror/rtx-5080-msi",
         seed_price=1319.00),
    dict(sku="GPU-5090-ASUS", name="ASUS ROG Astral RTX 5090", my_price=2049.00, cost=1650.00,
         floor_margin=0.08, competitor_url="https://example.com/newegg-mirror/rtx-5090-asus",
         seed_price=2049.00),
]


@pytest.fixture
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        for spec in SEED:
            session.add(Product(**spec, collector_id=COLLECTOR))
        session.commit()

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _run(client, **body) -> dict:
    response = client.post("/cycles/run", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _proposals(client, status: str) -> list[dict]:
    response = client.get("/proposals", params={"status": status})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------------------
# 0:00 - the product
# --------------------------------------------------------------------------------------

def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_products_carry_their_economics_and_staleness(client):
    products = client.get("/products").json()
    assert len(products) == 2

    msi = next(p for p in products if p["sku"] == "GPU-5080-MSI")
    assert msi["floor_price"] == 1134.00
    assert msi["margin_pct"] == pytest.approx(0.204, abs=1e-3)
    assert msi["last_confirmed_label"] == "never confirmed", "no cycle has run yet"
    assert msi["source_confirmed"] is True
    assert msi["held_proposal_id"] is None


# --------------------------------------------------------------------------------------
# 0:30 - the routine cycle and the bulk button
# --------------------------------------------------------------------------------------

def test_routine_cycle_then_approve_all_safe(client):
    summary = _run(client)
    assert [c["source_confirmed"] for c in summary["cycles"]] == [True, True]
    assert all(c["attempts"] == 0 for c in summary["cycles"]), "a healthy run must not heal"

    pending = _proposals(client, "pending")
    assert len(pending) == 2
    assert all(p["is_safe"] for p in pending)
    assert all(p["confidence"] == 100 for p in pending)
    assert all(p["guardian"] is None for p in pending), "no heal happened, so nothing to report"

    bulk = client.post("/proposals/approve-safe", json={}).json()
    assert bulk["applied_count"] == 2
    assert bulk["skipped"] == []

    msi = next(p for p in bulk["products"] if p["sku"] == "GPU-5080-MSI")
    assert msi["my_price"] == 1299.98, "a cent under the competitor's 1299.99"
    assert _proposals(client, "pending") == []


# --------------------------------------------------------------------------------------
# 1:00-1:45 - the break, and the catch
# --------------------------------------------------------------------------------------

@pytest.fixture
def held_card(client) -> dict:
    _run(client)
    client.post("/proposals/approve-safe", json={})
    _run(client, simulate_run="run_degraded",
         simulate_heal=["healed_swapped", "healed_swapped"])
    held = _proposals(client, "held")
    assert len(held) == 2, "both SKUs read the same broken collector"
    return next(h for h in held if h["product"]["sku"] == "GPU-5080-MSI")


def test_the_held_card_has_everything_it_needs_to_render(held_card):
    """Every value the card shows must come off this one response - no client-side joins, no
    hardcoded sentences in JSX."""
    assert held_card["status"] == "held"
    assert held_card["confidence"] == 40
    assert held_card["proposed_price"] == held_card["current_price"], "a hold never moves the price"
    assert "Rejected this heal" in held_card["reason"]
    assert held_card["is_safe"] is False

    guardian = held_card["guardian"]
    assert guardian["check_code"] == "COLUMN_SWAP"
    assert guardian["evidence"]["looks_like"] == "shipping"
    assert guardian["attempt"] == 2 and guardian["attempts_total"] == 2
    assert guardian["collector_id"] == COLLECTOR

    source = held_card["source"]
    assert source["confirmed"] is False
    assert source["observed_price"] == 19.99, "the row-level price the card quotes"
    assert "last confirmed" in source["last_confirmed_label"]


def test_a_degraded_run_reports_a_measured_trigger_reason(client):
    summary = _run(client, simulate_run="run_degraded",
                   simulate_heal=["healed_swapped", "healed_swapped"])
    assert "empty on 75% of rows" in summary["cycles"][0]["trigger_reason"]


def test_the_heal_log_speaks_scraper_studio(client, held_card):
    events = client.get("/heal-events").json()
    assert len(events) == 4, "two SKUs x two attempts"

    text = " | ".join(e["text"] for ev in events for e in ev["entries"])
    assert "awaiting approval" in text
    assert "COLUMN_SWAP" in text
    assert "re-prompted with the guardian's diagnosis" in text
    assert "previous collector retained" in text
    assert {e["kind"] for ev in events for e in ev["entries"]} <= {
        "run", "heal", "verdict", "commit", "reprompt"}


# --------------------------------------------------------------------------------------
# 1:45 - you cannot approve a held change by accident
# --------------------------------------------------------------------------------------

def test_approving_a_held_proposal_is_refused(client, held_card):
    response = client.post(f"/proposals/{held_card['id']}/approve")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["check_code"] == "COLUMN_SWAP"
    assert detail["confidence"] == 40

    still_held = _proposals(client, "held")
    assert held_card["id"] in [h["id"] for h in still_held]


def test_forcing_a_held_proposal_applies_the_floor_clamped_price(client, held_card):
    response = client.post(f"/proposals/{held_card['id']}/approve", params={"force": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied_price"] == 1134.00, "the engine's floor, never the competitor's 19.99"
    assert body["product"]["my_price"] == 1134.00
    assert body["proposal"]["status"] == "approved"


def test_skip_this_cycle_rejects_with_a_note(client, held_card):
    response = client.post(f"/proposals/{held_card['id']}/reject", params={"note": "skipped"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    assert "[skipped]" in response.json()["reason"]


def test_a_decided_proposal_cannot_be_decided_twice(client, held_card):
    client.post(f"/proposals/{held_card['id']}/reject")
    assert client.post(f"/proposals/{held_card['id']}/approve",
                       params={"force": True}).status_code == 409


# --------------------------------------------------------------------------------------
# 2:45 - the counterfactual
# --------------------------------------------------------------------------------------

def test_counterfactual_leads_with_the_floor_clamped_reality(held_card):
    cf = held_card["counterfactual"]
    assert cf is not None
    assert cf["competitor_price"] == 19.99
    assert cf["applied_price"] == 1134.00, "what OUR engine would have done"
    assert cf["naive_price"] == 19.98, "what a repricer with no floor rule would have done"
    assert cf["profit_delta_vs_now"] == -165.98, "the hero figure"
    assert cf["margin_pct_now"] > cf["margin_pct_applied"] > cf["margin_pct_naive"]


def test_the_chart_carries_a_real_gap_not_an_invented_line(client, held_card):
    product_id = held_card["product"]["id"]
    history = client.get(f"/products/{product_id}/history").json()
    points = history["points"]

    assert any(p["competitor_price"] is None for p in points), \
        "the unconfirmed cycle must be a hole in the data, not an interpolated value"
    assert all(p["confirmed"] is (p["competitor_price"] is not None) for p in points)
    assert history["counterfactual"]["applied_price"] == 1134.00


# --------------------------------------------------------------------------------------
# 3:30 - the resume beat
# --------------------------------------------------------------------------------------

def test_the_sharpened_prompt_recovers_and_the_hold_clears(client):
    _run(client)
    client.post("/proposals/approve-safe", json={})

    # a scalar hint means "fail once, then the guardian's sharper prompt works"
    summary = _run(client, simulate_run="run_degraded", simulate_heal="healed_swapped")

    assert all(c["source_confirmed"] for c in summary["cycles"])
    assert all(c["attempts"] == 2 for c in summary["cycles"])
    assert all(c["baseline_refreshed"] for c in summary["cycles"]), \
        "a verified heal may advance the yardstick"
    assert _proposals(client, "held") == [], "the hold clears once the source is confirmed again"

    events = client.get("/heal-events").json()
    reprompted = [e for e in events if e["attempt"] == 2]
    assert reprompted and all(e["verdict"] == "pass" for e in reprompted)
    assert all("rejected by validation" in e["prompt"] for e in reprompted)
    assert any("SHIPPING" in e["prompt"] for e in reprompted)


# --------------------------------------------------------------------------------------
# the demo hooks refuse to lie
# --------------------------------------------------------------------------------------

def test_an_unknown_simulate_key_is_rejected_at_the_door(client):
    response = client.post("/cycles/run", json={"simulate_heal": "healed_typo"})
    assert response.status_code == 422
    assert "healed_typo" in response.json()["detail"]["detail"]
    assert "healed_swapped" in response.json()["detail"]["known"]


def test_simulate_is_dropped_and_announced_when_mock_mode_is_off(client, monkeypatch):
    """Never silently honoured against a live collector - and the response says so out loud."""
    import json as _json

    from app.api import routes
    from app.scraper import brightdata

    rows = _json.loads(FIXTURES.read_text())["baseline"]
    # With mock_mode off, brightdata would shell out to the real CLI. Stub the collector run so this
    # test isolates the ROUTE's refusal to honour a simulate hint, not the CLI wrapper.
    monkeypatch.setattr(brightdata, "run", lambda cid, url, _simulate=None: rows)
    monkeypatch.setattr(routes.settings, "mock_mode", False)
    body = _run(client, simulate_heal="healed_swapped")

    assert body["mock_mode"] is False
    assert body["simulate_applied"] is None
    assert any("MOCK_MODE is off" in w for w in body["warnings"])


def test_unknown_sku_is_a_404(client):
    assert client.post("/cycles/run", json={"skus": ["NOPE"]}).status_code == 404


# --------------------------------------------------------------------------------------
# rehearsal
# --------------------------------------------------------------------------------------

def test_demo_reset_restores_the_opening_state(client, held_card):
    response = client.post("/demo/reset")
    assert response.status_code == 200, response.text

    assert _proposals(client, "held") == []
    assert _proposals(client, "pending") == []
    assert client.get("/heal-events").json() == []

    msi = next(p for p in client.get("/products").json() if p["sku"] == "GPU-5080-MSI")
    assert msi["my_price"] == 1319.00, "back to the seeded price"

    # and the whole arc runs again from a clean slate
    _run(client)
    assert len(_proposals(client, "pending")) == 2


def test_the_held_card_clears_when_a_later_cycle_confirms_the_source(client):
    """DEMO_SCRIPT 3:30 as the demo actually drives it: the break and the resume are two separate
    cycles, so the resume has to retire the hold the break left behind."""
    _run(client)
    client.post("/proposals/approve-safe", json={})

    _run(client, simulate_run="run_degraded",
         simulate_heal=["healed_swapped", "healed_swapped"])
    assert len(_proposals(client, "held")) == 2

    summary = _run(client, simulate_run="run_degraded", simulate_heal="healed_swapped")

    assert _proposals(client, "held") == [], "the held cards must clear on the resume beat"
    assert sum(len(c["superseded_proposal_ids"]) for c in summary["cycles"]) == 2
    assert len(_proposals(client, "pending")) == 2, "and a normal proposal takes their place"

    superseded = client.get("/proposals", params={"status": "superseded"}).json()
    assert len(superseded) == 2
    assert all("superseded" in p["reason"] for p in superseded)
