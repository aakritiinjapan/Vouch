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
    """Count trips through the approval gate so the loop's invariants are actually asserted.

    `approve` counts every accept and `publish` counts only the ones that carried
    save_to_production - the difference between landing a heal in a draft and putting it in front of
    customers, which is the whole subject of this file's second half.
    """
    calls = {"approve": 0, "reject": 0, "publish": 0}

    def approve(cid, *, save_to_production=False):
        calls["approve"] += 1
        if save_to_production:
            calls["publish"] += 1

    monkeypatch.setattr(brightdata, "approve_heal", approve)
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
    assert gate_calls == {"approve": 0, "reject": 0, "publish": 0}


def test_degraded_run_triggers_a_heal_with_a_measured_reason(product, baseline, gate_calls):
    """The trigger reason must be a fact the checks measured, not a sentence we typed."""
    outcome = run_cycle_for_product(product, baseline, simulate_run="run_degraded")

    assert outcome.healed
    assert "empty on 75% of rows" in outcome.trigger_reason
    assert outcome.verdict.decision == PASS, "the default mock heal is the good one"
    assert outcome.source_confirmed
    assert gate_calls == {"approve": 1, "reject": 0, "publish": 1}, \
        "the mock gate hands over a full run, so one accept both verifies and publishes"


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
    assert gate_calls == {"approve": 0, "reject": 2, "publish": 0}, \
        "one reject per failed attempt, no open gate, and nothing published"


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
    assert gate_calls == {"approve": 1, "reject": 1, "publish": 1}


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


# --------------------------------------------------------------------------------------
# full-page verification: what a heal has to prove before it reaches production
#
# Everything above this line runs against MOCK_MODE, whose fixture is a FULL-SIZE stand-in. That is
# the right call for a demo and useless for testing this half of the loop, because a full gate never
# produces a preview and so never reaches the branch where a heal must be re-run over the whole page
# before it may publish. Studio below is the real gate's shape: two rows and a population count.
# --------------------------------------------------------------------------------------

# One repointed selector, in the shape `scraper heal --legacy-output` returns. The summary this
# produces - "'price' now reads '.price-ship', the element 'shipping' read before" - is the sentence
# the 2026-08-23 study says is available at the gate, for free, when the values show nothing.
_TEMPLATE_A = """
function parse($) {
  const products = $('.product-card').map(function () {
    const $item = $(this);
    let name_text = $item.find('.title').text_sane();
    let price_text = $item.find('.price-current').text_sane();
    let ship_text = $item.find('.price-ship').text_sane();
    return { name: name_text, price: price_text, shipping: ship_text };
  }).get();
  return { products: products };
}
"""
_TEMPLATE_B_REPOINTED = _TEMPLATE_A.replace(
    "let price_text = $item.find('.price-current').text_sane();",
    "let price_text = $item.find('.price-ship').text_sane();")

REPOINTED_DIFF = {"template_a": {"steps": [{"parse_code": _TEMPLATE_A}]},
                  "template_b": {"steps": [{"parse_code": _TEMPLATE_B_REPOINTED}]}}


class Studio:
    """A Scraper Studio that never leaves the process, and that MODELS THE DRAFT.

    `production` is what an ordinary run returns; `draft` is what `--version dev` returns. Publishing
    actually moves production, so a test can assert on the state of the world rather than only on
    the calls that were made. `leaks_on_approve` makes an ordinary accept move production too, which
    is the inference the loop refuses to take on trust: the CLI source proves what is SENT, and only
    a read-back can say what the API did with it.

    `full_gate` hands the whole page over at the gate, the way MOCK_MODE and a short page both do.
    """

    def __init__(self, *, production, preview, draft, raw_diff=None, leaks_on_approve=False,
                 draft_run_raises=False, full_gate=False):
        self.production = list(production)
        self.preview = list(preview)
        self.draft = list(draft)
        self.raw_diff = raw_diff
        self.leaks_on_approve = leaks_on_approve
        self.draft_run_raises = draft_run_raises
        self.full_gate = full_gate
        self.log: list[str] = []

    def install(self, monkeypatch):
        monkeypatch.setattr(brightdata, "run", self.run)
        monkeypatch.setattr(brightdata, "propose_heal", self.propose_heal)
        monkeypatch.setattr(brightdata, "approve_heal", self.approve_heal)
        monkeypatch.setattr(brightdata, "reject_heal", self.reject_heal)
        return self

    def run(self, collector, url, _simulate=None, *, version=None):
        self.log.append("run:dev" if version == "dev" else "run")
        if version == "dev":
            if self.draft_run_raises:
                raise RuntimeError("collector run timed out")
            return list(self.draft)
        return list(self.production)

    def propose_heal(self, collector, prompt, url, _simulate=None, *, capture_diff=False):
        self.log.append("heal")
        assert capture_diff, "the source diff is free at the gate; the loop must always ask for it"
        rows = self.draft if self.full_gate else self.preview
        return brightdata.HealProposal(
            collector_id=collector, proposed_records=list(rows), pending=True,
            is_sample=not self.full_gate, preview_rows=len(rows),
            population_rows=len(self.draft), raw_diff=self.raw_diff,
            gate_status="pending_answer")

    def approve_heal(self, collector, *, save_to_production=False):
        self.log.append("approve:publish" if save_to_production else "approve:draft")
        if save_to_production or self.leaks_on_approve:
            self.production = list(self.draft)

    def reject_heal(self, collector):
        self.log.append("reject")

    @property
    def page_loads(self) -> int:
        return sum(1 for entry in self.log if entry.startswith("run"))


# Production is the DEGRADED run throughout this section, because that is the only state a real
# cycle heals from - and it is what gives the production probe something to recognise. A collector
# that was already fine and a healed template that is also fine extract the same shape, and the
# probe correctly reports that there is nothing to tell apart (DRAFT_MOOT); it takes a real before
# and after for "did accepting this publish it" to be a question with an answer.
@pytest.fixture
def clean_heal(monkeypatch):
    """A preview that says nothing, over a full page that is genuinely fine."""
    return Studio(production=_fixture("run_degraded"), preview=_fixture("healed_good")[:2],
                  draft=_fixture("healed_good")).install(monkeypatch)


@pytest.fixture
def misleading_heal(monkeypatch):
    """The study's headline, in the shape the loop sees it.

    Two clean-looking rows at the gate; the delivery charge in the `price` field across the whole
    page. The old loop scored this PASS 100/100 and then read the competitor's price off the two
    rows. Nothing here may reach production.
    """
    return Studio(production=_fixture("run_degraded"), preview=_fixture("baseline")[:2],
                  draft=_fixture("healed_swapped")).install(monkeypatch)


def _heal(product, baseline, **kwargs):
    """Force the heal path without a degradation, so each test's subject is the gate, not the run."""
    kwargs.setdefault("max_heal_attempts", 1)
    return run_cycle_for_product(product, baseline, simulate_heal="forced", **kwargs)


def test_a_good_heal_is_verified_on_the_whole_page_before_it_is_published(product, baseline,
                                                                          clean_heal):
    outcome = _heal(product, baseline)

    assert clean_heal.log == ["run", "heal", "approve:draft", "run:dev", "run", "approve:publish"], \
        "accept into a draft, read the whole page, prove production is untouched, only then publish"
    assert outcome.source_confirmed
    assert outcome.records == _fixture("healed_good"), "the full run, never the two preview rows"
    assert outcome.competitor_price == 1289.99
    assert clean_heal.production == _fixture("healed_good"), "and the collector really is fixed"


def test_the_price_is_read_off_the_page_and_not_off_the_gate(product, baseline, monkeypatch):
    """The second half of the old defect, on its own.

    With 2 of 30 rows the product being priced may not even be in the preview - so a loop that
    priced off the gate would return no price at all here, or worse, some other card's. The full run
    contains it, because it contains everything.
    """
    full = _fixture("healed_good")
    studio = Studio(production=_fixture("run_degraded"), preview=full[3:5], draft=full)
    studio.install(monkeypatch)
    outcome = _heal(product, baseline)

    assert product.name not in {row["name"] for row in studio.preview}, \
        "the previewed tiles are not this product"
    assert outcome.competitor_price == 1289.99, "and the price still comes back, off the full page"


def test_the_verdict_that_confirms_is_the_one_that_saw_everything(product, baseline, clean_heal):
    attempt = _heal(product, baseline).heal_attempts[0]

    assert attempt.rows_from == orchestrator.ROWS_FROM_FULL_RUN
    assert attempt.verdict.decision == PASS
    assert attempt.verdict.evidence.is_full and attempt.verdict.full_battery
    assert attempt.gate_verdict.confirmed is False, "the preview never confirmed anything"
    assert attempt.gate_verdict.decision == REVIEW
    assert attempt.preview_rows == 2
    assert attempt.draft_probe == orchestrator.DRAFT_HELD


def test_the_added_cost_is_the_two_page_loads_this_module_advertises(product, baseline, clean_heal):
    """The comment on PAGE_LOADS_TO_VERIFY_A_HEAL, made executable, so it cannot quietly drift."""
    _heal(product, baseline)
    assert clean_heal.page_loads == 1 + orchestrator.PAGE_LOADS_TO_VERIFY_A_HEAL


def test_a_heal_that_previews_clean_and_fails_the_page_is_never_published(product, baseline,
                                                                          misleading_heal):
    """The measured failure, run through the fixed loop."""
    outcome = _heal(product, baseline)

    assert "approve:publish" not in misleading_heal.log
    assert misleading_heal.production == _fixture("run_degraded"), "production was never touched"
    assert outcome.source_confirmed is False
    assert outcome.verdict.decision == FAIL
    assert outcome.verdict.primary_failure.code == "COLUMN_SWAP"
    assert outcome.competitor_price is None, "an unconfirmed source must not yield a price"
    assert outcome.proposal.status == "held"


def test_the_gate_verdict_on_those_same_rows_would_have_confirmed_nothing(product, baseline,
                                                                          misleading_heal):
    """Why the extra page load exists: the preview found nothing, and finding nothing is not a pass."""
    attempt = _heal(product, baseline).heal_attempts[0]

    assert attempt.gate_verdict.failures == [], "the two rows objected to nothing at all"
    assert attempt.gate_verdict.confirmed is False
    assert attempt.verdict.decision == FAIL, "and the whole page said COLUMN_SWAP"


def test_a_heal_the_preview_already_rejects_pays_for_no_extra_pages(product, baseline, monkeypatch):
    """A preview can reject, and rejecting early is the one thing it is good for."""
    studio = Studio(production=_fixture("baseline"), preview=_fixture("healed_swapped")[:2],
                    draft=_fixture("healed_swapped")).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert studio.log == ["run", "heal", "reject"], "no accept, no draft run, no probe"
    assert studio.page_loads == 1, "a rejected heal never pays for a page it did not need"
    assert outcome.heal_attempts[0].rows_from == orchestrator.ROWS_FROM_PREVIEW
    assert outcome.verdict.decision == FAIL
    assert outcome.source_confirmed is False


def test_a_draft_approve_that_actually_publishes_is_caught_and_held(product, baseline, monkeypatch):
    """The inference, disproven at runtime. The rows are FINE and it is held anyway.

    What failed is not the heal, it is the mechanism that is supposed to keep an unverified heal out
    of production. Moving money through a control we have just measured as absent is the thing this
    product exists not to do, so the price stays where it is and the alarm says which of the two
    problems this is.
    """
    studio = Studio(production=_fixture("run_degraded"), preview=_fixture("healed_good")[:2],
                    draft=_fixture("healed_good"), leaks_on_approve=True).install(monkeypatch)
    outcome = run_cycle_for_product(product, baseline, simulate_heal="forced")

    assert "approve:publish" not in studio.log, "we never asked for this"
    assert outcome.source_confirmed is False
    assert outcome.competitor_price is None
    assert outcome.proposal.status == "held"
    assert outcome.control_alarm is not None and "PUBLISHED" in outcome.control_alarm
    assert "PUBLISHED" in outcome.verdict.brief
    assert outcome.heal_attempts[0].draft_probe == orchestrator.DRAFT_PUBLISHED
    assert outcome.heal_attempts[0].in_production is True, "it is live, whether we wanted it or not"
    assert len(outcome.heal_attempts) == 1, \
        "no re-prompt: never spend another heal on a collector that just published itself"


def test_a_full_run_that_cannot_be_obtained_holds_the_price(product, baseline, monkeypatch):
    """'If a full run cannot be obtained, the source is unconfirmed and the price does not move.'"""
    studio = Studio(production=_fixture("baseline"), preview=_fixture("baseline")[:2],
                    draft=_fixture("healed_good"), draft_run_raises=True).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert "approve:publish" not in studio.log
    assert studio.log[-1] == "reject", "the accepted heal is withdrawn rather than left sitting"
    assert outcome.source_confirmed is False
    assert outcome.competitor_price is None
    assert outcome.heal_attempts[0].rows_from == orchestrator.ROWS_FROM_NOTHING
    assert outcome.heal_attempts[0].verdict.evidence.rows_judged == 0
    assert "Couldn't confirm this heal" in outcome.verdict.brief


# --------------------------------------------------------------------------------------
# the template diff: an escalation trigger, never a judgement
# --------------------------------------------------------------------------------------

def test_a_repointed_selector_never_rejects_a_heal_the_page_agrees_with(product, baseline,
                                                                        monkeypatch):
    """P1 in the study reported a swap and was CORRECT - the page moved and the healer followed.

    The source cannot tell that apart from being talked into a swap, so it may escalate and it may
    explain, but the values are what decide.
    """
    studio = Studio(production=_fixture("baseline"), preview=_fixture("baseline")[:2],
                    draft=_fixture("healed_good"), raw_diff=REPOINTED_DIFF).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert outcome.source_confirmed, "a repoint is not evidence of harm"
    assert "approve:publish" in studio.log
    assert outcome.heal_attempts[0].template_diff["semantic"] is True


def test_a_repoint_forces_the_full_run_even_when_the_gate_showed_everything(product, baseline,
                                                                            monkeypatch):
    """The escalation, at the only place it can bite: a gate that already had full evidence.

    Without the source diff this publishes straight off the gate, which is correct on the evidence.
    With it, one field demonstrably reads a different element, and one more page load is cheap
    against re-reading the values that field now produces.
    """
    studio = Studio(production=_fixture("baseline"), preview=[], draft=_fixture("healed_good"),
                    raw_diff=REPOINTED_DIFF, full_gate=True).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert "run:dev" in studio.log, "the source said a field moved, so the page had to be re-read"
    assert outcome.source_confirmed
    assert outcome.heal_attempts[0].rows_from == orchestrator.ROWS_FROM_FULL_RUN


def test_a_full_gate_with_no_repoint_needs_no_extra_page(product, baseline, monkeypatch):
    """MOCK_MODE's path, stated as the general rule it actually is: if we saw all of it, we saw it."""
    studio = Studio(production=_fixture("baseline"), preview=[], draft=_fixture("healed_good"),
                    full_gate=True).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert studio.log == ["run", "heal", "approve:publish"]
    assert outcome.heal_attempts[0].rows_from == orchestrator.ROWS_FROM_GATE
    assert outcome.source_confirmed


def test_the_diff_summary_is_carried_into_the_verdict_whatever_the_verdict_is(product, baseline,
                                                                              monkeypatch):
    """It is the most actionable sentence available, and a rejection is when it is most wanted."""
    studio = Studio(production=_fixture("baseline"), preview=_fixture("baseline")[:2],
                    draft=_fixture("healed_swapped"), raw_diff=REPOINTED_DIFF).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert outcome.verdict.decision == FAIL
    assert "'price' now reads '.price-ship'" in outcome.verdict.brief
    assert "the element 'shipping' read before" in outcome.verdict.brief
    assert "approve:publish" not in studio.log


def test_a_cosmetic_diff_says_nothing_and_changes_nothing(product, baseline, monkeypatch):
    """The healthy-page probe changed comments and a numeric guard. Reporting that as a change is
    how a warning channel teaches people to ignore it."""
    cosmetic = {"template_a": {"steps": [{"parse_code": _TEMPLATE_A}]},
                "template_b": {"steps": [{"parse_code": _TEMPLATE_A.replace(
                    "const $item = $(this);", "// the card\n    const $item = $(this);")}]}}
    studio = Studio(production=_fixture("baseline"), preview=[], draft=_fixture("healed_good"),
                    raw_diff=cosmetic, full_gate=True).install(monkeypatch)
    outcome = _heal(product, baseline)

    assert studio.log == ["run", "heal", "approve:publish"], "no escalation from a comment"
    assert outcome.heal_attempts[0].template_diff["semantic"] is False
    assert "source:" not in outcome.verdict.brief


# --------------------------------------------------------------------------------------
# the production probe, on its own terms
# --------------------------------------------------------------------------------------

def test_two_runs_of_one_template_still_look_like_one_template():
    """Live pages move. A probe that called overnight drift a template change would be deleted."""
    before = _fixture("baseline")
    after = [{**row, "price": row["price"] * 1.07, "in_stock": not row["in_stock"]}
             for row in before]
    assert orchestrator._same_extraction(before, after)


def test_a_repointed_field_does_not_look_like_the_same_template():
    assert not orchestrator._same_extraction(_fixture("baseline"), _fixture("healed_swapped"))


def test_a_dropped_field_does_not_look_like_the_same_template():
    stripped = [{k: v for k, v in row.items() if k != "shipping"} for row in _fixture("baseline")]
    assert not orchestrator._same_extraction(_fixture("baseline"), stripped)


@pytest.mark.parametrize("production,expected", [
    ("baseline", orchestrator.DRAFT_HELD),
    ("healed_swapped", orchestrator.DRAFT_PUBLISHED),
    ("run_degraded", orchestrator.DRAFT_UNPROVEN),
])
def test_the_probe_names_what_it_found(production, expected):
    """Production matching neither reference is UNPROVEN, not 'held' - and unproven never publishes."""
    assert orchestrator._probe_draft(_fixture("baseline"), _fixture("healed_swapped"),
                                     _fixture(production)) == expected


def test_a_heal_that_changes_nothing_measurable_has_nothing_to_prove():
    """Whether an accept published a template that extracts the same shape cannot matter."""
    assert orchestrator._probe_draft(_fixture("baseline"), _fixture("baseline"),
                                     _fixture("healed_swapped")) == orchestrator.DRAFT_MOOT
