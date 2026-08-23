"""
Calibrate the heal-lab before it is used to make claims about Bright Data.

Two instruments are checked here, and a tally built on either of them being wrong would be worse
than no data at all - it would let us assert a pattern that is an artefact of our own measurement.

  `_classify` decides which baseline field a heal's output actually resembles. It is checked against
  corruptions whose right answer we already know.

  The PREVIEW/FULL comparison decides whether a heal that passed Bright Data's one-row approval gate
  was broken on the other 29 rows. That is the lab's headline claim, so the row-1 overfit it exists
  to catch is constructed here and the harness is required to catch it.

Nothing in this file may touch the network. `brightdata._cli` is stubbed to raise in every test that
goes near the gather path, so a missing stub fails loudly instead of spending credits.
"""

import json
import sys
from pathlib import Path

import pytest

TESTBED = Path(__file__).resolve().parents[2] / "testbed"
sys.path.insert(0, str(TESTBED))

from app.config import settings  # noqa: E402
from app.guardian.checks import profile_run  # noqa: E402
from app.scraper import brightdata  # noqa: E402
from scripts import heal_lab  # noqa: E402
from scripts.heal_lab import PROMPT_FAMILIES, _classify  # noqa: E402

from generate import apply_variant, base_rows, render  # noqa: E402
from verify import parse  # noqa: E402

CLEAN_URL = "https://voltmart.test/"
P1_URL = "https://voltmart.test/p1/"


@pytest.fixture(scope="module")
def clean_rows():
    return parse(render(apply_variant(base_rows(), "clean"), "clean"))


@pytest.fixture(scope="module")
def baseline(clean_rows):
    return profile_run(clean_rows)


def _variant(name):
    return parse(render(apply_variant(base_rows(), name), name))


def _row1_overfit(rows):
    """Hypothesis P1, made concrete: correct on row 1, the shipping line on every row after it.

    This is the shape the one-row gate cannot see. It is written here rather than taken from the
    testbed's variants because the testbed corrupts every row - a whole-page swap is visible in a
    one-row preview, and the entire point of this case is that it is not.
    """
    out = [dict(r) for r in rows]
    for r in out[1:]:
        r["price"] = r["shipping"]
    return out


def _swapped_preview(rows):
    """A one-row preview that a one-row preview can actually be judged on.

    The sampled row matters. Row 0 of the testbed ships at $24.99 against a $14.99 median, which is
    67% away - outside MAX_LABEL_DISTANCE - so a price/shipping swap SAMPLED FROM THE FLAGSHIP TILE
    cannot be labelled and reads as clean. That is a true property of the gate, not a quirk of this
    helper, and it is why these tests sample a row whose shipping sits on the median.
    """
    row = next(r for r in rows if r["shipping"] == 14.99)
    return [{**row, "price": row["shipping"]}]


def _names_collapsed(rows):
    """Every name pinned to one string, prices untouched - a break the price column is innocent of."""
    return [{**r, "name": "Voltmart Graphics Card"} for r in rows]


# --------------------------------------------------------------------------------------
# The classifier
# --------------------------------------------------------------------------------------

def test_an_honest_page_is_labelled_as_its_own_field(clean_rows, baseline):
    got = _classify(clean_rows, baseline)
    assert got["looks_like"] == "price"
    assert got["distances"]["price"] < got["distances"]["shipping"]


def test_a_price_shipping_swap_is_labelled_shipping(baseline):
    """The canonical mis-heal: the healer grabbed the delivery line."""
    got = _classify(_variant("swap"), baseline)
    assert got["looks_like"] == "shipping"


def test_a_crossed_out_swap_is_not_labelled_shipping(baseline):
    """price <-> original_price differ by only 5-30%, so the label must not drift to a far field.

    It may legitimately land on `price` (the two are close by construction) - what would be WRONG is
    calling it `shipping` or `rating`, because that would invent a mis-heal of a kind that did not
    happen and put it in the tally.
    """
    got = _classify(_variant("inverted"), baseline)
    assert got["looks_like"] in {"price", "original_price"}
    assert got["looks_like"] not in {"shipping", "rating"}


def test_a_4x_inflation_is_reported_as_explained_by_nothing(baseline):
    """Drift is not a swap, and the label must not pretend otherwise.

    4x the price lands arithmetically NEARER baseline `original_price` than baseline `price`, simply
    because original_price is the higher field. Naming it would put a swap in the tally that never
    happened. So the proximity guard has to refuse the label and say what the nearest field was.
    """
    got = _classify(_variant("drift"), baseline)
    assert got["looks_like"] is None, "an inflation must not be labelled as a swap"
    assert got["nearest"] is not None, "but the nearest field is still worth recording"
    assert "no baseline field explains" in got["reason"]


def test_a_dropped_price_is_reported_as_unclassifiable_not_guessed(baseline):
    """No price means no label. Guessing here would manufacture evidence."""
    rows = [{k: v for k, v in r.items() if k != "price"} for r in _variant("clean")]
    got = _classify(rows, baseline)
    assert got["looks_like"] is None
    assert "not numeric" in got["reason"]


def test_a_nulled_price_is_reported_as_unclassifiable(baseline):
    rows = [{**r, "price": None} for r in _variant("clean")]
    got = _classify(rows, baseline)
    assert got["looks_like"] is None


def test_classifying_an_empty_run_does_not_raise(baseline):
    assert _classify([], baseline)["looks_like"] is None


def test_every_prompt_family_names_the_price_field():
    """A prompt that never mentions price is not probing what the lab claims to probe."""
    for family, prompt in PROMPT_FAMILIES.items():
        assert "price" in prompt.lower(), family


def test_the_misleading_families_are_actually_misleading():
    """These carry the prompt axis: clear instructions that are WRONG.

    If the healer obeys them it trusts the prompt over the page, which is a far more useful finding
    than "vague prompts are risky" - so they must not accidentally be phrased as good advice.
    """
    crossed = PROMPT_FAMILIES["misleading_crossed"].lower()
    assert "crossed-out" in crossed and "correct price" in crossed

    shipping = PROMPT_FAMILIES["misleading_shipping"].lower()
    assert "delivery charge" in shipping and "correct price" in shipping

    control = PROMPT_FAMILIES["control_sharp"].lower()
    assert "not the shipping cost" in control, "the control must exclude what the others invite"


def test_every_prompt_family_is_inside_the_cli_prompt_cap():
    """The CLI's PROMPT_MAX_LEN is 1000 and it 400s past it, after provisioning the job."""
    for family, prompt in PROMPT_FAMILIES.items():
        assert len(prompt) <= brightdata.MAX_HEAL_PROMPT_CHARS, family


# --------------------------------------------------------------------------------------
# The clean/dirty predicate, which the whole comparison rests on
# --------------------------------------------------------------------------------------

def test_a_correct_one_row_preview_is_not_scored_dirty_for_being_one_row(clean_rows, baseline):
    """The load-bearing property of `_clean`, and the easiest thing to get wrong.

    Row 0 of the testbed is the $1,999 flagship against a $565 catalogue median. On one row the
    distance function compares medians only, so a perfectly correct extraction sits 2.5 away from
    its own baseline field and cannot be labelled. If that counted as dirty, no preview would ever
    be clean, no gap could ever be observed, and the lab would silently measure its own sample size.
    """
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    assert preview["price_looks_like"] is None, "one row cannot support a label - that is expected"
    # REVIEW, not PASS: the guardian will not confirm on partial evidence, however clean it looks.
    # That is the correct product behaviour and it is deliberately NOT what `_clean` measures here -
    # the lab is asking what the GATE showed, and the gate showed nothing wrong. See _clean.
    assert preview["decision"] == "review"
    assert preview["codes"] == [], "nothing came back wrong, which is the gate's whole story"
    assert preview["clean"] is True


def test_a_preview_that_names_another_field_is_dirty_even_if_the_verdict_passes(baseline):
    """A positive label on some other field is evidence, and it outranks a passing verdict."""
    m = {"price_looks_like": "shipping", "decision": "pass", "codes": [], "distances": {}}
    assert heal_lab._clean(m) is False


def test_a_failing_verdict_is_dirty_even_without_a_label(baseline):
    m = {"price_looks_like": None, "decision": "fail", "codes": ["NULL_SPIKE"], "distances": {}}
    assert heal_lab._clean(m) is False


# --------------------------------------------------------------------------------------
# The measurement the lab exists for: one row said yes, thirty rows said no
# --------------------------------------------------------------------------------------

def test_a_row1_overfit_is_invisible_to_the_preview_and_caught_by_the_full_run(clean_rows, baseline):
    """P1, end to end through the instrument. If this fails the lab cannot see its own hypothesis."""
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    full = heal_lab._measure(_row1_overfit(clean_rows), baseline, len(clean_rows), is_sample=False)

    assert preview["clean"] is True, "the gate had no reason to refuse this"
    assert full["clean"] is False, "the whole page did"
    assert heal_lab._blind_spot_kind(preview, full) == "row1_overfit"


def test_the_overfit_is_not_filed_as_a_volume_artefact(clean_rows, baseline):
    """The trap this classification has to avoid, spelled out.

    Reading shipping on rows 2-30 drags the price median from $565 to $15 and reports only
    NUMERIC_DRIFT - which is on the list of codes a one-row preview structurally cannot emit. A rule
    that looked at codes alone would therefore file the flagship result under "volume artefact" and
    the banner would report zero. Asking which FIELD the failure names is what saves it.
    """
    full = heal_lab._measure(_row1_overfit(clean_rows), baseline, len(clean_rows), is_sample=False)
    assert set(full["codes"]) <= heal_lab.SAMPLE_BLIND_CODES, "the premise of this test"
    assert full["price_codes"] == ["NUMERIC_DRIFT"], "and it names the price column"
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    assert heal_lab._blind_spot_kind(preview, full) == "row1_overfit"


def test_a_medium_only_defect_never_registers_as_a_gap(clean_rows, baseline):
    """Every name pinned to one string, every price correct - and no gap is reported.

    CARDINALITY_COLLAPSE is MEDIUM, which costs 10 points and still leaves a PASS, so the guardian
    would have accepted this run. Pinned because it bounds the headline: the blind-spot count is
    "heals the guardian would have refused on the full page", not "heals with any defect at all".
    """
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    full = heal_lab._measure(_names_collapsed(clean_rows), baseline, len(clean_rows),
                             is_sample=False)
    assert "CARDINALITY_COLLAPSE" in full["codes"]
    assert full["decision"] == "pass" and full["clean"] is True
    assert heal_lab._blind_spot_kind(preview, full) is None


def test_the_bucket_rule_separates_a_price_break_from_everything_else():
    """The rule itself, on constructed measurements, so all three outcomes are pinned exactly."""
    clean_preview = {"price_looks_like": None, "decision": "pass", "codes": [], "price_codes": []}

    def full(**over):
        base = {"price_looks_like": None, "decision": "fail", "codes": [], "price_codes": []}
        return {**base, **over}

    assert heal_lab._blind_spot_kind(
        clean_preview, full(codes=["NULL_SPIKE"], price_codes=["NULL_SPIKE"])) == "row1_overfit"
    assert heal_lab._blind_spot_kind(
        clean_preview, full(price_looks_like="shipping", codes=["COLUMN_SWAP"])) == "row1_overfit"
    assert heal_lab._blind_spot_kind(
        clean_preview, full(codes=["ROW_COUNT_SHIFT"])) == "volume_only"
    assert heal_lab._blind_spot_kind(
        clean_preview, full(codes=["NULL_SPIKE"])) == "other_field"


def test_a_truncated_run_is_charged_to_the_price_column_and_that_overstates_it(clean_rows, baseline):
    """A known false positive, pinned here so it is a documented limit and not a surprise.

    Twelve of thirty rows, every price correct, and the guardian still reports COLUMN_SWAP on
    `price`: the profile distance uses min and max, and a subset that drops the $89 card and keeps
    the $1,999 one moves both. So a heal that merely returned a SHORT run is filed as a row-1
    overfit. The direction is right (the gate hid a real break) but the label overstates the cause,
    and any P1 count read off this log has to be checked against the row counts.
    """
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    full = heal_lab._measure(clean_rows[:12], baseline, len(clean_rows), is_sample=False)
    assert "ROW_COUNT_SHIFT" in full["codes"]
    assert "COLUMN_SWAP" in full["price_codes"], "the guardian's own false positive on a subset"
    assert heal_lab._blind_spot_kind(preview, full) == "row1_overfit"


def test_a_heal_that_is_clean_on_every_row_reports_no_gap(clean_rows, baseline):
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    full = heal_lab._measure(clean_rows, baseline, len(clean_rows), is_sample=False)
    assert full["clean"] is True
    assert heal_lab._blind_spot_kind(preview, full) is None


def test_no_gap_is_claimed_when_the_full_run_was_never_measured(clean_rows, baseline):
    preview = heal_lab._measure(clean_rows[:1], baseline, len(clean_rows), is_sample=True)
    assert heal_lab._blind_spot_kind(preview, None) is None


# --------------------------------------------------------------------------------------
# The page axis
# --------------------------------------------------------------------------------------

def test_a_page_spec_parses_into_name_url_and_collector():
    page = heal_lab.parse_page_spec("p1=https://volt.test/p1/?x=1@c_abc")
    assert page.name == "p1"
    assert page.url == "https://volt.test/p1/?x=1", "a query string must not be eaten by the split"
    assert page.collector == "c_abc"


@pytest.mark.parametrize("spec", [
    "https://volt.test/@c_abc",          # no name
    "p1=https://volt.test/",             # no collector
    "p1=volt.test@c_abc",                # not a url
    "=https://volt.test/@c_abc",         # empty name
    "p1=https://volt.test/@",            # empty collector
])
def test_a_malformed_page_spec_is_refused_rather_than_guessed(spec):
    with pytest.raises(ValueError):
        heal_lab.parse_page_spec(spec)


def test_the_page_named_clean_is_the_control_by_default():
    args = _args(page=[f"clean={CLEAN_URL}@c_a", f"p1={P1_URL}@c_b"])
    pages = heal_lab.pages_from_args(args)
    assert [p.is_control for p in pages] == [True, False]


def test_the_single_page_shorthand_is_never_promoted_to_control():
    """Pointed at a broken page, a silent control would license a page finding that is not one."""
    args = _args(collector="c_a", url=P1_URL, page_name="p1")
    pages = heal_lab.pages_from_args(args)
    assert pages[0].is_control is False


def test_a_control_naming_a_page_that_is_not_in_the_run_is_refused():
    args = _args(page=[f"clean={CLEAN_URL}@c_a"], control="typo")
    with pytest.raises(ValueError):
        heal_lab.pages_from_args(args)


# --------------------------------------------------------------------------------------
# Driving `gather`, with Bright Data stubbed out entirely
# --------------------------------------------------------------------------------------

def _args(**over):
    """The argparse namespace `gather` expects, with the defaults main() would have supplied."""
    base = dict(page=None, control=None, collector=None, url=None, page_name="unnamed",
                repeat=1, prompts=None, commit_and_measure=None, page_cost=1,
                max_credits=heal_lab.DEFAULT_MAX_CREDITS, dry_run=False, analyse=False)
    base.update(over)
    return type("Args", (), base)()


class FakeStudio:
    """A Scraper Studio that never leaves the process.

    `production_rows` is what a plain run returns and `draft_rows` what `--version dev` returns, so a
    test can make the draft differ from production exactly the way an accepted-but-unsaved heal
    would. `leak_on_approve` makes approving change production too, which is the failure the whole
    committing protocol is built to detect.
    """

    def __init__(self, production_rows, preview_rows, draft_rows, *, leak_on_approve=False,
                 template_a="t_prod"):
        self.production_rows = production_rows
        self.preview_rows = preview_rows
        self.draft_rows = draft_rows
        self.leak_on_approve = leak_on_approve
        self.template_a = template_a
        self.calls = []

    def install(self, monkeypatch):
        monkeypatch.setattr(brightdata, "run", self.run)
        monkeypatch.setattr(brightdata, "propose_heal", self.propose_heal)
        monkeypatch.setattr(brightdata, "approve_heal", self.approve_heal)
        monkeypatch.setattr(brightdata, "reject_heal", self.reject_heal)
        return self

    def run(self, collector, url, _simulate=None, *, version=None):
        self.calls.append(("run", collector, version))
        return list(self.draft_rows if version == "dev" else self.production_rows)

    def propose_heal(self, collector, prompt, url, _simulate=None, *, capture_diff=False):
        self.calls.append(("heal", collector, capture_diff))
        assert capture_diff, "the diff is free evidence; the lab must always ask for it"
        return brightdata.HealProposal(
            collector_id=collector, proposed_records=list(self.preview_rows), pending=True,
            is_sample=True, gate_status="pending_answer",
            raw_diff={"template_a": {"steps": [self.template_a]},
                      "template_b": {"steps": ["s1", "s2"]}},
        )

    def approve_heal(self, collector, *, save_to_production=False):
        self.calls.append(("approve", collector, save_to_production))
        assert not save_to_production, "the draft protocol depends on never saving to production"
        if self.leak_on_approve:
            self.production_rows = list(self.draft_rows)

    def reject_heal(self, collector):
        self.calls.append(("reject", collector, None))

    def verbs(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Point the log at a temp file, force the live path, and make any real CLI call a test failure."""
    monkeypatch.setattr(heal_lab, "LOG", tmp_path / "heal_lab.jsonl")
    monkeypatch.setattr(settings, "mock_mode", False)

    def never(*_a, **_k):
        raise AssertionError("the Bright Data CLI must never be invoked from a test")

    monkeypatch.setattr(brightdata, "_cli", never)
    return heal_lab.LOG


def _records(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_the_default_gather_path_rejects_every_heal_and_commits_nothing(lab, monkeypatch, clean_rows):
    studio = FakeStudio(clean_rows, clean_rows[:1], _row1_overfit(clean_rows)).install(monkeypatch)

    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--page", f"p1={P1_URL}@c_b",
                   "--prompts", "control_sharp"])

    assert "approve" not in studio.verbs(), "the default path must never accept a heal"
    assert studio.verbs().count("reject") == 2
    records = _records(lab)
    assert len(records) == 2
    for rec in records:
        assert rec["mode"] == "reject"
        assert rec["committed"] is False
        assert rec["rejected"] is True
        assert rec["full"] is None if "full" in rec else True
        assert rec["preview"]["rows"] == 1


def test_a_trial_records_the_page_the_url_and_the_collector_it_ran_against(lab, monkeypatch,
                                                                          clean_rows):
    FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--page", f"p1={P1_URL}@c_b",
                   "--prompts", "control_sharp"])

    by_page = {r["page"]: r for r in _records(lab)}
    assert by_page["clean"]["url"] == CLEAN_URL
    assert by_page["clean"]["collector_id"] == "c_a"
    assert by_page["clean"]["is_control_page"] is True
    assert by_page["p1"]["collector_id"] == "c_b"
    assert by_page["p1"]["is_control_page"] is False
    assert by_page["p1"]["baseline_page"] == "clean", "one ruler, cut from the control page"


def test_the_template_diff_is_captured_without_approving_anything(lab, monkeypatch, clean_rows):
    """P3's evidence is free: it needs no approval and it is in every record."""
    FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    heal_lab.main(["--collector", "c_a", "--url", CLEAN_URL, "--prompts", "control_sharp"])

    rec = _records(lab)[0]
    assert rec["diff"]["template_b"]["steps"] == ["s1", "s2"]
    assert rec["template_a_hash"] and rec["template_b_hash"]
    assert rec["template_a_hash"] != rec["template_b_hash"]
    assert rec["template_b_steps"] == 2


def test_commit_mode_approves_reads_the_draft_and_leaves_production_alone(lab, monkeypatch,
                                                                         clean_rows):
    studio = FakeStudio(clean_rows, clean_rows[:1], _row1_overfit(clean_rows)).install(monkeypatch)

    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--prompts", "control_sharp",
                   "--commit-and-measure", heal_lab.CONFIRM_TOKEN])

    assert studio.verbs() == ["run", "heal", "approve", "run", "run"], studio.calls
    assert ("run", "c_a", "dev") in studio.calls, "the full measurement must read the DRAFT"
    assert "reject" not in studio.verbs()

    rec = _records(lab)[0]
    assert rec["committed"] is True
    assert rec["full_version"] == "dev"
    assert rec["production_unchanged"] is True
    assert rec["preview"]["clean"] is True
    assert rec["full"]["clean"] is False
    assert rec["blind_spot"] == "row1_overfit"
    assert rec["started_from_first_template"] is True


def test_an_approve_that_reaches_production_aborts_the_run(lab, monkeypatch, clean_rows, capsys):
    """The inference this mode rests on, checked rather than trusted.

    If approving without --auto-save turns out to change production, every later trial would be a
    heal of a healed collector. Recording those as if they were independent samples is the one
    outcome worse than gathering nothing, so the run stops.
    """
    studio = FakeStudio(clean_rows, clean_rows[:1], _row1_overfit(clean_rows),
                        leak_on_approve=True).install(monkeypatch)

    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--prompts", "control_sharp,vague_generic",
                   "--commit-and-measure", heal_lab.CONFIRM_TOKEN])

    records = _records(lab)
    assert len(records) == 1, "the second trial must not have run"
    assert "draft_assumption_failed" in records[0]
    assert records[0]["full"]["clean"] is False, "the measurement taken before the abort is kept"
    out = capsys.readouterr().out
    assert "RUN ABORTED" in out
    assert "changed PRODUCTION" in out
    assert studio.verbs().count("heal") == 1


def test_commit_mode_refuses_a_mistyped_token(lab, monkeypatch, clean_rows):
    studio = FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    with pytest.raises(SystemExit):
        heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--commit-and-measure", "yes"])
    assert studio.calls == [], "nothing may be called before the token is checked"


def test_a_plan_over_the_budget_cap_refuses_to_start(lab, monkeypatch, clean_rows):
    studio = FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    with pytest.raises(SystemExit):
        heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--page-cost", "97",
                       "--max-credits", "10"])
    assert studio.calls == []


def test_dry_run_spends_nothing_and_still_prints_the_estimate(lab, monkeypatch, clean_rows, capsys):
    studio = FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--page", f"p1={P1_URL}@c_b",
                   "--prompts", "control_sharp", "--dry-run",
                   "--commit-and-measure", heal_lab.CONFIRM_TOKEN])

    assert studio.calls == [], "a dry run must not call Bright Data at all"
    out = capsys.readouterr().out
    assert "est. cost" in out and "credits" in out
    assert "COMMIT to draft" in out
    assert not lab.exists(), "and it must not write a record"


def test_mock_mode_still_refuses_to_pretend_it_healed_anything(tmp_path, monkeypatch, clean_rows):
    monkeypatch.setattr(heal_lab, "LOG", tmp_path / "heal_lab.jsonl")
    monkeypatch.setattr(settings, "mock_mode", True)
    studio = FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    with pytest.raises(SystemExit):
        heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--prompts", "control_sharp"])
    assert studio.calls == []


def test_a_failed_heal_is_recorded_and_the_gate_is_still_answered(lab, monkeypatch, clean_rows):
    studio = FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)

    def boom(*_a, **_k):
        studio.calls.append(("heal", "c_a", True))
        raise RuntimeError("AI-Flow said 429")

    monkeypatch.setattr(brightdata, "propose_heal", boom)
    heal_lab.main(["--collector", "c_a", "--url", CLEAN_URL, "--prompts", "control_sharp"])

    rec = _records(lab)[0]
    assert rec["ok"] is False
    assert "429" in rec["error"]
    assert rec["rejected"] is True, "an errored heal must still not be left sitting at the gate"


# --------------------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------------------

SCHEMA_1_RECORD = {
    "at": "2026-08-01T00:00:00+00:00", "collector_id": "c_old", "url": CLEAN_URL,
    "family": "vague_generic", "repetition": 1, "prompt": "the price field looks wrong",
    "baseline_rows": 30, "ok": True, "seconds": 412.0, "preview_rows": 1,
    "extracted": {"price": 14.99}, "price_looks_like": "shipping", "price_median": 14.99,
    "distances": {"price": 0.97, "shipping": 0.0}, "decision": "fail", "confidence": 40,
    "codes": ["COLUMN_SWAP"], "rejected": True,
}


def test_analyse_reads_schema_1_records_without_crashing(lab, capsys):
    """The old log is real data. A schema change that discards it is a change that loses evidence."""
    lab.write_text(json.dumps(SCHEMA_1_RECORD) + "\n", encoding="utf-8")
    heal_lab.main(["--analyse"])

    out = capsys.readouterr().out
    assert "(unlabelled)" in out, "a record with no page must not claim to have one"
    assert "NO CONTROL PAGE" in out, "and must not be treated as a control"
    assert "vague_generic" in out and "shipping" in out


def test_analyse_names_a_page_defect_only_when_the_control_survived(lab, monkeypatch, clean_rows,
                                                                    capsys):
    studio = FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    # The control page heals cleanly; the adversarial page returns the shipping column instead.
    original = studio.propose_heal

    def per_page(collector, prompt, url, _simulate=None, *, capture_diff=False):
        proposal = original(collector, prompt, url, capture_diff=capture_diff)
        if url == P1_URL:
            proposal.proposed_records = _swapped_preview(clean_rows)
        return proposal

    monkeypatch.setattr(brightdata, "propose_heal", per_page)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--page", f"p1={P1_URL}@c_b",
                   "--prompts", "control_sharp"])
    capsys.readouterr()

    heal_lab.main(["--analyse"])
    out = capsys.readouterr().out
    assert "PAGE DEFECT" in out
    assert "[preview-only]" in out, "a page verdict from one row must be marked as weak"


def test_analyse_does_not_blame_the_page_when_the_control_failed_too(lab, monkeypatch, clean_rows,
                                                                     capsys):
    """A failure on both pages is a bad collector or a bad prompt. The page gets no credit for it."""
    FakeStudio(clean_rows, _swapped_preview(clean_rows), clean_rows).install(monkeypatch)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--page", f"p1={P1_URL}@c_b",
                   "--prompts", "control_sharp"])
    capsys.readouterr()

    heal_lab.main(["--analyse"])
    out = capsys.readouterr().out
    assert "PAGE DEFECT" not in out
    assert "control failed too" in out


def test_analyse_headlines_the_heals_that_passed_the_gate_and_were_broken(lab, monkeypatch,
                                                                          clean_rows, capsys):
    FakeStudio(clean_rows, clean_rows[:1], _row1_overfit(clean_rows)).install(monkeypatch)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--prompts", "control_sharp",
                   "--commit-and-measure", heal_lab.CONFIRM_TOKEN])
    capsys.readouterr()

    heal_lab.main(["--analyse"])
    out = capsys.readouterr().out
    assert "PASSED THE ONE-ROW GATE AND WERE BROKEN ON THE FULL PAGE: 1 of 1" in out
    assert "production verified unchanged" in out


def test_analyse_flags_a_draft_run_that_never_differed_from_production(lab, monkeypatch,
                                                                       clean_rows, capsys):
    """The silent failure the mode is most exposed to.

    If `--version dev` does not actually address the draft, the "full run" is production, every gap
    reads as zero, and nothing looks wrong. The draft and production rows are both already in hand,
    so noticing costs nothing - and a run of zeros has to be labelled unproven, not negative.
    """
    FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--prompts", "control_sharp",
                   "--commit-and-measure", heal_lab.CONFIRM_TOKEN])
    capsys.readouterr()

    rec = _records(lab)[0]
    assert rec["draft_matches_production"] is True
    assert rec["heal_proposed_a_change"] is True

    heal_lab.main(["--analyse"])
    out = capsys.readouterr().out
    assert "did not read the draft" in out
    assert "UNPROVEN" in out


def test_analyse_says_the_blind_spot_is_unmeasured_when_nothing_was_committed(lab, monkeypatch,
                                                                              clean_rows, capsys):
    """Silence is not evidence of absence, and the report has to say which one it is."""
    FakeStudio(clean_rows, clean_rows[:1], clean_rows).install(monkeypatch)
    heal_lab.main(["--page", f"clean={CLEAN_URL}@c_a", "--prompts", "control_sharp"])
    capsys.readouterr()

    heal_lab.main(["--analyse"])
    out = capsys.readouterr().out
    assert "gate blind spot: UNMEASURED" in out
    assert heal_lab.CONFIRM_TOKEN in out


# --------------------------------------------------------------------------------------
# The wrapper additions the lab depends on
# --------------------------------------------------------------------------------------

@pytest.fixture
def cli_recorder(monkeypatch):
    """Capture the argv the wrapper would hand the CLI, and answer with a canned envelope."""
    calls = []
    replies = {}

    def fake_cli(*args):
        calls.append(list(args))
        return replies.get(args[1], "[]")

    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(brightdata, "_cli", fake_cli)
    return calls, replies


def test_run_asks_for_the_draft_only_when_a_version_is_given(cli_recorder):
    calls, _ = cli_recorder
    brightdata.run("c_a", CLEAN_URL)
    brightdata.run("c_a", CLEAN_URL, version="dev")
    assert "--version" not in calls[0], "existing callers must be untouched"
    assert calls[1][-2:] == ["--version", "dev"]


def test_approve_never_saves_to_production_unless_asked(cli_recorder):
    calls, _ = cli_recorder
    brightdata.approve_heal("c_a")
    brightdata.approve_heal("c_a", save_to_production=True)
    assert "--auto-save" not in calls[0], "the draft protocol depends on this default"
    assert "--auto-save" in calls[1]


def test_capture_diff_reads_the_gate_through_the_legacy_payload(cli_recorder):
    """--legacy-output reports the raw status `pending_answer`, not the envelope's spelling."""
    calls, replies = cli_recorder
    replies["heal"] = json.dumps({
        "status": "pending_answer",
        "preview_result": [{"price": 1999.99}],
        "diff": {"template_a": {"steps": [1]}, "template_b": {"steps": [1, 2, 3]}},
    })
    proposal = brightdata.propose_heal("c_a", "fix the price", CLEAN_URL, capture_diff=True)

    assert "--legacy-output" in calls[0]
    assert proposal.gate_status == "pending_answer"
    assert proposal.raw_diff["template_b"]["steps"] == [1, 2, 3]
    assert "3 step(s)" in proposal.diff_summary, "the envelope's summary is rebuilt, not lost"
    assert proposal.is_sample is True


def test_a_heal_that_did_not_stop_at_the_gate_is_still_refused(cli_recorder):
    _, replies = cli_recorder
    replies["heal"] = json.dumps({"status": "done", "preview_result": [{"price": 1}]})
    with pytest.raises(RuntimeError, match="approval gate"):
        brightdata.propose_heal("c_a", "fix it", CLEAN_URL, capture_diff=True)


def test_an_over_long_heal_prompt_is_refused_before_the_call(cli_recorder):
    calls, _ = cli_recorder
    with pytest.raises(ValueError, match="1000"):
        brightdata.propose_heal("c_a", "x" * 1001, CLEAN_URL)
    assert calls == [], "the CLI 400s on this only after provisioning the job"
