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

import copy
import json
from pathlib import Path

import pytest

from app.scraper import brightdata

ROWS = [{"name": "MSI RTX 5080 Gaming Trio", "price": 1299.99, "shipping": 19.99}]

# Raw payloads captured from six real heals on 2026-08-23 (docs/research/, written up in
# FINDINGS.md). These are the ground truth for everything below the "the real gate payload" heading.
#
# They are load-bearing, not illustrative. Every one of the defects those tests pin shipped because
# the fixtures in THIS file were plausible inventions - a flat top-level array, one row per product,
# no elision marker - and the gate does not return that shape. A hand-written approximation of a
# payload is a statement about what we expect, and expectations are exactly what was wrong. If these
# files go missing the tests below must fail loudly rather than skip; losing the evidence is a
# bigger problem than a red build.
RESEARCH = Path(__file__).resolve().parents[2] / "docs" / "research"

# Every captured heal. Named rather than globbed so the set under test cannot silently shrink.
CAPTURED_HEALS = [
    "heal_legacy_probe.json",     # the --legacy-output probe that first exposed the nested shape
    "heal_p1.json",               # first-tile overfit    (falsified)
    "heal_p2.json",               # positional anchoring  (mechanism confirmed, failure not)
    "heal_p3.json",               # stale cached DOM      (falsified)
    "heal_mislead_shipping.json", # "the price is the delivery charge" - broke it, price := $24.99
    "heal_mislead_crossed.json",  # "the price is the crossed-out number" - broke it too
]


def captured(name: str) -> dict:
    """One raw heal payload, exactly as the CLI emitted it."""
    return json.loads((RESEARCH / name).read_text(encoding="utf-8"))


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


# --------------------------------------------------------------------------------------
# the REAL approval-gate payload
#
# Everything above this line was written from what we expected Bright Data to return. Everything
# below is written from what it actually returned, and the gap between the two is where three
# defects lived. The shape, from docs/research/heal_*.json:
#
#     [ { "products": [ {tile 1}, {tile 2}, "28 more items" ] } ]
#
# One envelope record, a container named by the AI, two product dicts, and a literal string standing
# in for the other 28 rows.
# --------------------------------------------------------------------------------------

def test_the_real_gate_payload_yields_the_two_products_not_one_container():
    """The regression that matters most, on the payload that exposed it.

    Before the fix `_rows` returned `[{"products": [...]}]` - a single row whose only key was
    `products`. The guardian profiled that row, found no `price` field, and reported FIELD_MISSING /
    FAIL 0-100. It rejected a genuinely dangerous heal, which looks like the system working, but its
    stated reason was that the price field had vanished; in truth `price` was present and held the
    delivery charge. A verdict that is right by accident tells the operator to go looking in the
    wrong place, and cannot be trusted the next time it is right.
    """
    payload = captured("heal_mislead_shipping.json")["preview_result"]

    rows = brightdata._rows(payload)

    assert len(rows) == 2, "two product tiles, not one container"
    assert all(isinstance(r, dict) for r in rows)
    assert [r["name"] for r in rows] == [
        "Voltmart RTX 5090 Founders Edition 32GB GDDR7",
        "Voltmart RTX 5080 Stormbringer 16GB GDDR7",
    ]
    assert "products" not in rows[0], "the container is unwrapped, not carried as a field"
    # The actual defect this heal introduced, now visible to the guardian: price IS present, and it
    # is the shipping figure. Same row, same number, twice.
    assert rows[0]["price"] == 24.99 and rows[0]["shipping"] == 24.99
    assert rows[1]["price"] == 19.99 and rows[1]["shipping"] == 19.99


@pytest.mark.parametrize("name", CAPTURED_HEALS)
def test_every_captured_heal_unwraps_to_two_dict_rows(name):
    """All six heals, not just the interesting one - the shape is the collector's, not the prompt's."""
    rows = brightdata._rows(captured(name)["preview_result"])

    assert len(rows) == 2
    assert all(isinstance(r, dict) for r in rows), "a string can never be a row"
    assert all("name" in r and "price" in r for r in rows)
    assert all("products" not in r for r in rows)


@pytest.mark.parametrize("name", CAPTURED_HEALS)
def test_the_elision_marker_never_reaches_the_guardian_as_data(name):
    """The marker is a note ABOUT the rows, not one of them.

    Passed through it would be profiled as a product record: a str with no fields, dragging every
    field's null rate up and inventing a NULL_SPIKE finding out of the gate's own formatting.
    """
    rows = brightdata._rows(captured(name)["preview_result"])
    assert "28 more items" not in rows
    assert not any(isinstance(r, str) for r in rows)


@pytest.mark.parametrize("name", CAPTURED_HEALS)
def test_money_objects_are_scalarised_once_the_container_is_unwrapped(name):
    """`_flatten` always knew how to reduce {value, currency}; the nesting bug meant it never saw one.

    Two defects stacked so that fixing either alone would have looked like no progress - which is the
    reason to pin them together, on the same payload.
    """
    rows = brightdata._rows(captured(name)["preview_result"])
    for row in rows:
        assert isinstance(row["price"], float), f"{row['price']!r} is still a money object"
        assert row.get("original_price") is None or isinstance(row["original_price"], float)


# --------------------------------------------------------------------------------------
# the population the gate hid
# --------------------------------------------------------------------------------------

def test_the_marker_recovers_the_true_page_size():
    """2 previewed + 28 elided = 30, and 30 is independently verifiable.

    collector_p1.json is a full run of the same page by the same collector before any heal: exactly
    30 rows. So the number read out of the string is not merely self-consistent, it matches a
    separately captured ground truth.
    """
    elided = brightdata._elided_rows(captured("heal_mislead_shipping.json")["preview_result"])
    assert elided == 28

    full_page = json.loads((RESEARCH / "collector_p1.json").read_text(encoding="utf-8"))["rows"]
    assert len(full_page) == 30, "the page really does have 30 tiles"
    assert 2 + elided == len(full_page)


def test_the_proposal_carries_how_much_of_the_page_was_judged(live):
    """propose_heal end to end on the raw captured envelope, CLI stubbed out.

    This is the fact the product used to discard: the verdict is formed on 2 of 30 rows - 6.7%, and
    the FIRST 6.7%, which on a price-sorted catalogue is the expensive end. An evidence-sufficiency
    rule needs the denominator before it can say any of that.
    """
    _, cli = live
    cli.output = json.dumps(captured("heal_mislead_shipping.json"))

    proposal = brightdata.propose_heal("c_mt5gwa3w1eknnqzr2", "prompt", "https://x/p1.html")

    assert proposal.preview_rows == 2
    assert proposal.population_rows == 30
    assert proposal.is_sample is True
    assert proposal.preview_rows == len(proposal.proposed_records), "the count is of the rows given"
    # The legacy payload reports the raw gate status and carries no view_url; both must still work,
    # or capture_diff silently breaks the gate check the architecture rests on.
    assert proposal.gate_status == "pending_answer"
    assert proposal.view_url.endswith("c_mt5gwa3w1eknnqzr2")


def test_population_is_unknown_rather_than_guessed_when_the_gate_says_nothing():
    """The real payload with its marker deleted. No marker means we do not know, not that we saw all.

    Reporting 2 here would be the worst available answer: it would claim the preview IS the page and
    make a heal judged on 6.7% of the rows look fully evidenced.
    """
    payload = copy.deepcopy(captured("heal_mislead_shipping.json")["preview_result"])
    payload[0]["products"] = [p for p in payload[0]["products"] if isinstance(p, dict)]

    assert brightdata._elided_rows(payload) is None
    assert len(brightdata._rows(payload)) == 2, "the rows still arrive; only the count is unknown"


def test_an_unreadable_marker_forfeits_the_count_but_not_the_rows():
    """The real payload with its marker reworded. Degrade to None, never to a partial sum."""
    payload = copy.deepcopy(captured("heal_mislead_shipping.json")["preview_result"])
    payload[0]["products"][-1] = "and many more"

    assert brightdata._elided_rows(payload) is None
    assert len(brightdata._rows(payload)) == 2, "an unrecognised entry costs the count, not the data"


@pytest.mark.parametrize("marker,expected", [
    ("28 more items", 28),           # exactly what the gate sent
    ("1 more item", 1),              # the singular, which the gate would have to use at n=1
    ("  28 more items  ", 28),       # padding does not change the number
    ("28 More Items", 28),           # nor does casing
    ("0 more items", 0),
])
def test_the_marker_is_read_when_it_is_unambiguous(marker, expected):
    assert brightdata._elided_count(marker) == expected


@pytest.mark.parametrize("marker", [
    "many more items",               # no number
    "1,234 more items",              # a separator whose meaning is locale-dependent
    "28 items",                      # does not say ADDITIONAL, and the marker is an increment
    "28 more items (truncated)",     # unrecognised suffix - not the format we validated
    "more items",
    "28",
    "-5 more items",
    "",
    None,                            # not a string at all
    12,
    {"more": 28},
])
def test_anything_less_than_unambiguous_is_refused(marker):
    """A wrong population is worse than no population: it is a confident understatement of how much
    of the page went unseen, and it would silently satisfy a sufficiency rule built on top of it."""
    assert brightdata._elided_count(marker) is None


def test_a_marker_outside_a_record_list_is_not_evidence_about_rows():
    """Only a list that holds records can be eliding records. A stray string field is prose."""
    assert brightdata._elided_rows({"note": "28 more items"}) is None
    assert brightdata._elided_rows({"tags": ["28 more items", "clearance"]}) is None


# --------------------------------------------------------------------------------------
# the flat collector must not regress
# --------------------------------------------------------------------------------------

def test_the_real_newegg_run_still_passes_through_flat():
    """96 rows the live Newegg collector actually returned, flat at the top level with no container.

    The nesting fix is a change to what counts as a container, so this is the shape it could
    plausibly have broken. Pinned against the real run rather than a two-row stand-in.
    """
    fixtures = Path(brightdata.__file__).resolve().parents[2] / "tests" / "fixtures"
    baseline = json.loads((fixtures / "newegg_live.json").read_text(encoding="utf-8"))["baseline"]

    assert len(baseline) == 96
    assert brightdata._rows(baseline) == baseline, "already flat: unchanged, not re-shaped"
    assert brightdata._elided_rows(baseline) is None, "a full run elides nothing and says nothing"


def test_a_list_of_scalars_is_a_field_value_not_a_container():
    """The relaxed container test must not start treating every list as rows.

    `_container_records` requires at least one dict; a list of strings has none, so it stays a field.
    """
    rows = brightdata._rows([{"name": "a", "price": 1.0, "tags": ["clearance", "bundle"]}])

    assert len(rows) == 1
    assert rows[0]["tags"] == ["clearance", "bundle"]


def test_an_empty_container_leaves_the_record_alone():
    """`{"products": []}` says nothing was found, which is a row with no products, not zero rows."""
    rows = brightdata._rows([{"products": [], "product_page_url": "https://example.com/list"}])

    assert len(rows) == 1
    assert rows[0]["product_page_url"].endswith("/list")


# --------------------------------------------------------------------------------------
# the currency guard, through the shape it will actually meet
# --------------------------------------------------------------------------------------

def test_the_currency_guard_reaches_through_the_container_and_the_marker():
    """Derived from the real payload by changing ONE nested currency code.

    The guard has to see a code two levels down, inside a container the old code could not even
    unwrap, in a list that also holds a non-dict. Everything else about the payload is untouched.
    """
    payload = copy.deepcopy(captured("heal_mislead_shipping.json")["preview_result"])
    payload[0]["products"][1]["price"]["currency"] = "CAD"

    with pytest.raises(RuntimeError, match="CAD"):
        brightdata._rows(payload)


@pytest.mark.parametrize("name", CAPTURED_HEALS)
def test_the_real_payloads_are_all_usd_so_the_guard_stays_quiet(name):
    """The guard must not fire on the payloads it will actually see; a false stop is a dead cycle."""
    assert brightdata._currencies(captured(name)["preview_result"]) == {"USD"}


# --------------------------------------------------------------------------------------
# approve: draft versus production
# --------------------------------------------------------------------------------------

def test_approve_does_not_ask_for_a_save_unless_told_to(live):
    """Verified against @brightdata/cli v0.3.5 dist/commands/scraper.js, resume_and_poll:

        const resume_body = approve && opts.autoSave
            ? { message: approve, auto_save: true }
            : { message: approve };

    so `--auto-save` is the only thing that puts auto_save in the resume body. Whether omitting it
    leaves production serving the old template is INFERRED from the docs and unconfirmed - which is
    exactly why the default must not move without someone deciding to move it.
    """
    calls, _ = live

    brightdata.approve_heal("c_abc")
    brightdata.approve_heal("c_abc", save_to_production=True)

    assert "--auto-save" not in calls[0], "the default must not commit to production on an inference"
    assert "--auto-save" in calls[1], "and the caller who wants production must be able to say so"


def test_reject_never_carries_auto_save(live):
    """The CLI's own comment: auto_save only takes effect on approval, the API ignores it on reject."""
    calls, _ = live
    brightdata.reject_heal("c_abc")
    assert "--auto-save" not in calls[0]


def test_the_draft_can_be_read_back_without_publishing_it(live):
    """`run(..., version="dev")` is the cheap way to see what an approved-but-unsaved heal produces:
    the full page, not the gate's two rows, and no publish."""
    calls, cli = live
    cli.output = json.dumps({"result": ROWS})

    brightdata.run("c_abc", "https://example.com/x", version="dev")

    assert "--version" in calls[0] and "dev" in calls[0]


# --------------------------------------------------------------------------------------
# mock mode reports the same pair, honestly
# --------------------------------------------------------------------------------------

def test_the_mock_proposal_reports_a_full_population(monkeypatch):
    """The fixture is a full-size stand-in, so nothing is elided BY CONSTRUCTION and the population
    is the row count. This is the one place population_rows may be filled in without a marker, and
    it is sound for a reason that does not generalise to the live path."""
    monkeypatch.setattr(brightdata.settings, "mock_mode", True)

    proposal = brightdata.propose_heal("c_x", "p", "https://x")

    assert proposal.is_sample is False
    assert proposal.preview_rows == len(proposal.proposed_records) > 0
    assert proposal.population_rows == proposal.preview_rows
