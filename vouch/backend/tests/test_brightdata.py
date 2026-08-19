"""
The Bright Data wrapper's live path.

MOCK_MODE means these code paths never run during the demo, which is exactly why they need tests -
they will run for the first time against a real collector, under time pressure, on hackathon day.

What they pin:
  - the heal envelope must be at the approval gate and must carry preview_result, or we refuse it
    rather than validating nothing and calling it a pass;
  - approve/reject must carry the collector id (the CLI signature takes it);
  - --auto-approve must never be sent, because it commits without the gate this product exists for.
"""

from __future__ import annotations

import json

import pytest

from app.scraper import brightdata

ROWS = [{"name": "MSI RTX 5080 Gaming Trio", "price": 1299.99, "shipping": 19.99}]


@pytest.fixture
def live(monkeypatch):
    """Force the real path and capture the CLI argv instead of executing it."""
    monkeypatch.setattr(brightdata.settings, "mock_mode", False)
    calls: list[tuple[str, ...]] = []

    def fake_cli(*args: str) -> str:
        calls.append(args)
        return fake_cli.output

    fake_cli.output = "{}"
    monkeypatch.setattr(brightdata, "_cli", fake_cli)
    return calls, fake_cli


# --------------------------------------------------------------------------------------
# the approval gate
# --------------------------------------------------------------------------------------

def test_heal_returns_the_preview_rows_from_the_gate(live):
    calls, cli = live
    cli.output = json.dumps({
        "collector_id": "c_abc",
        "status": "awaiting_approval",
        "preview_result": ROWS,
        "diff_summary": "proposed template has 1 step(s)",
        "view_url": "https://brightdata.com/cp/scrapers/c_abc",
    })

    proposal = brightdata.propose_heal("c_abc", "re-capture price", "https://example.com/x")

    assert proposal.proposed_records == ROWS
    assert proposal.pending is True
    assert proposal.diff_summary.startswith("proposed template")
    assert proposal.view_url.endswith("c_abc")

    argv = calls[0]
    assert argv[:3] == ("scraper", "heal", "c_abc")
    assert "--auto-approve" not in argv, "committing without the gate would delete the whole product"


def test_a_heal_that_already_committed_is_refused(live):
    """If the gate did not hold, there is nothing to validate - fail loudly instead of passing air."""
    _, cli = live
    cli.output = json.dumps({"collector_id": "c_abc", "status": "done", "preview_result": ROWS})

    with pytest.raises(RuntimeError, match="did not stop at the approval gate"):
        brightdata.propose_heal("c_abc", "prompt", "https://example.com/x")


def test_a_gate_without_preview_rows_is_refused(live):
    _, cli = live
    cli.output = json.dumps({"collector_id": "c_abc", "status": "awaiting_approval",
                             "diff_summary": "1 step"})

    with pytest.raises(RuntimeError, match="no preview_result"):
        brightdata.propose_heal("c_abc", "prompt", "https://example.com/x")


# --------------------------------------------------------------------------------------
# approve / reject carry the collector id
# --------------------------------------------------------------------------------------

def test_approve_and_reject_pass_the_collector_id(live):
    calls, _ = live

    brightdata.approve_heal("c_abc")
    brightdata.reject_heal("c_abc")

    assert calls[0][:3] == ("scraper", "approve", "c_abc")
    assert "--reject" not in calls[0]
    assert calls[1][:3] == ("scraper", "approve", "c_abc")
    assert "--reject" in calls[1]


def test_create_collector_returns_the_c_star_id(live):
    calls, cli = live
    cli.output = json.dumps({"collector_id": "c_mp7x8a9b", "status": "done"})

    collector_id = brightdata.create_collector(
        "https://example.com/listing", "item name, sale price, shipping cost", name="vouch-gpus")

    assert collector_id == "c_mp7x8a9b"
    argv = calls[0]
    assert argv[:2] == ("scraper", "create")
    assert "--name" in argv and "vouch-gpus" in argv


def test_create_collector_without_an_id_is_an_error(live):
    _, cli = live
    cli.output = json.dumps({"status": "failed"})
    with pytest.raises(RuntimeError, match="no collector_id"):
        brightdata.create_collector("https://example.com/x", "fields")


# --------------------------------------------------------------------------------------
# envelope shape tolerance
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    ROWS,
    {"result": ROWS},
    {"results": ROWS},
    {"data": ROWS},
    {"rows": ROWS},
    {"records": ROWS},
    {"preview_result": ROWS},
])
def test_rows_accepts_every_documented_envelope_shape(payload):
    """The run and heal envelopes differ and have changed across CLI releases. Guessing one shape and
    breaking on the day is a worse failure than accepting several."""
    assert brightdata._rows(payload) == ROWS


def test_rows_rejects_something_that_holds_no_rows():
    with pytest.raises(RuntimeError, match="could not find extracted rows"):
        brightdata._rows("just a string")


def test_rows_drops_non_dict_entries():
    assert brightdata._rows([*ROWS, "junk", None]) == ROWS


# --------------------------------------------------------------------------------------
# mock mode stays inert
# --------------------------------------------------------------------------------------

def test_mock_mode_never_shells_out(monkeypatch):
    def explode(*_args):
        raise AssertionError("MOCK_MODE must not invoke the CLI")

    monkeypatch.setattr(brightdata, "_cli", explode)
    monkeypatch.setattr(brightdata.settings, "mock_mode", True)

    assert brightdata.create_collector("https://x", "fields").startswith("c_")
    assert brightdata.run("c_x", "https://x")
    assert brightdata.propose_heal("c_x", "p", "https://x").proposed_records
    assert brightdata.approve_heal("c_x") is None
    assert brightdata.reject_heal("c_x") is None


def test_npx_resolution_explains_itself_when_node_is_missing(monkeypatch):
    monkeypatch.setattr(brightdata.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="npx not found"):
        brightdata._npx()


# --------------------------------------------------------------------------------------
# flattening Scraper Studio's real output shape
# --------------------------------------------------------------------------------------

# Exactly what the live Newegg collector returned. The AI named its container after what it found,
# nested one product inside it, echoed the request as `input`, and returned price as a money object.
STUDIO_SHAPE = [
    {
        "graphics_cards": [{
            "name": "ASRock Challenger Radeon RX 7600 8GB GDDR6",
            "price": {"value": 299.99, "currency": "USD", "symbol": "$"},
            "shipping": 0,
            "rating": 4,
            "in_stock": True,
        }],
        "product_page_url": "https://www.newegg.com/p/N82E16814930093",
        "input": {"url": "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48"},
    },
]


def test_the_real_studio_shape_flattens_to_one_row_per_product():
    rows = brightdata._rows(STUDIO_SHAPE)

    assert len(rows) == 1
    row = rows[0]
    assert row["price"] == 299.99, "the money object is reduced to its number"
    assert row["name"].startswith("ASRock")
    assert row["shipping"] == 0
    assert row["in_stock"] is True
    assert row["product_page_url"].endswith("N82E16814930093"), "outer fields describe the product"
    assert "input" not in row, "the echoed request is metadata, not data"
    assert "graphics_cards" not in row, "the container is unwrapped, not carried"


def test_a_container_holding_several_products_explodes_into_several_rows():
    payload = [{
        "products": [
            {"name": "a", "price": {"value": 1.0, "currency": "USD"}},
            {"name": "b", "price": {"value": 2.0, "currency": "USD"}},
        ],
        "product_page_url": "https://example.com/list",
    }]
    rows = brightdata._rows(payload)

    assert [r["name"] for r in rows] == ["a", "b"]
    assert [r["price"] for r in rows] == [1.0, 2.0]
    assert all(r["product_page_url"].endswith("/list") for r in rows), "carried onto each"


def test_already_flat_rows_pass_through_unchanged():
    flat = [{"name": "a", "price": 10.0, "shipping": 0.0}]
    assert brightdata._rows(flat) == flat


@pytest.mark.parametrize("money,expected", [
    ({"value": 12.5, "currency": "USD", "symbol": "$"}, 12.5),
    ({"amount": 12.5, "currency": "USD"}, 12.5),
    ({"price": 12.5}, 12.5),
    ({"currency": "USD"}, {"currency": "USD"}),      # nothing numeric: left alone
    (12.5, 12.5),
    ("$12.50", "$12.50"),                            # strings are _coerce_number's job, not ours
])
def test_scalarise_reduces_money_objects(money, expected):
    assert brightdata._scalarise(money) == expected


def test_a_boolean_is_not_mistaken_for_a_money_value():
    """bool is a subclass of int, so a naive isinstance check would unwrap {"value": True}."""
    assert brightdata._scalarise({"value": True}) == {"value": True}


# --------------------------------------------------------------------------------------
# the currency guard
# --------------------------------------------------------------------------------------

def test_a_non_usd_price_is_refused_outright():
    """newegg.ca does not redirect to .com and serves a different catalogue in CAD. Accepting those
    numbers as USD would silently poison price history - refusing is the only safe response."""
    payload = [{"cards": [{"name": "x", "price": {"value": 999.0, "currency": "CAD"}}]}]
    with pytest.raises(RuntimeError, match="CAD"):
        brightdata._rows(payload)


def test_the_refusal_explains_what_to_check():
    payload = [{"cards": [{"name": "x", "price": {"value": 1.0, "currency": "JPY"}}]}]
    with pytest.raises(RuntimeError, match="regional storefront"):
        brightdata._rows(payload)


def test_usd_in_any_casing_is_accepted():
    payload = [{"cards": [{"name": "x", "price": {"value": 1.0, "currency": "usd"}}]}]
    assert brightdata._rows(payload)[0]["price"] == 1.0


def test_rows_without_any_currency_are_accepted():
    """Most collectors never emit a currency field at all; absence is not a failure."""
    assert brightdata._rows([{"name": "x", "price": 1.0}])[0]["price"] == 1.0
