"""
The loop. For each product:

    1. run its competitor collector
    2. if the run looks degraded, heal - and let NOTHING reach production until the healed template
       has been run over the WHOLE page and judged on that run
    3. if the guardian rejects, feed its own diagnosis back as a sharper heal prompt and retry
    4. only trusted competitor prices reach the pricing engine
    5. produce a reprice proposal the seller reviews (or a HELD one if the source is unconfirmed)

Step 2 in full, because it is the step that moves money:

    propose_heal(capture_diff=True)         the gate: preview rows AND the healer's own source diff,
                                            both inside a job already paid for
    a cheap pre-filter on the preview       it may REJECT outright; it may never confirm
    approve_heal(save_to_production=False)  the accepted heal lands in a DRAFT
    run(..., version="dev")                 the whole page, as the healed template really produces it
    a probe of production                   proves, for THIS approve, that the draft did not publish
    the guardian, over those full-page rows full evidence, full battery
    approve_heal(save_to_production=True)   only now, and only if that verdict confirms

Why it is built this way, measured rather than argued (docs/research/FINDINGS.md). The gate hands
over the first two tiles of thirty. A heal that had put the delivery charge in the `price` field
scored PASS 100/100 on those two rows; the same heal over all thirty is COLUMN_SWAP, FAIL 40/100.
This module used to commit on that preview and then read the competitor's price out of the same two
rows - two defects compounding, because with 2 of 30 the product being priced may not even be
present. `decide` now caps partial evidence below PASS, which stops the first defect on its own, and
this loop deliberately does not lean on it: a cap is a tunable policy in the guardian, and this is
the code path that spends money. It enforces the property in its own terms instead. `records` never
come from a preview, and nothing is published on a verdict that did not see the whole page. If a
full run cannot be obtained, the source is unconfirmed and the price does not move - that is the
product working, not the product failing.

This module is deliberately PURE. It reads attributes off the rows it is handed and returns
dataclasses; it may import models for type annotations, but it never opens a Session and never
commits - app/service.py owns every write. That split is what lets the whole cycle, including the
retry loop, be exercised against unsaved Product/Baseline instances with no database at all.

It is also free of `settings.mock_mode` branching: the mock/real split lives entirely inside
scraper/brightdata.py, so this file reads the same whether you are demoing or in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional, Sequence, Union

from app.guardian import judge
from app.guardian.checks import Evidence, FieldProfile, profile_run, run_all_checks
from app.guardian.template_diff import ExtractionStatus, TemplateDiff, diff_templates
from app.guardian.verdict import (
    FAIL,
    PARTIAL_EVIDENCE_CEILING,
    REVIEW,
    Verdict,
    apply_judge,
    decide,
)
from app.models import Baseline, Product
from app.pricing import engine
from app.scraper import brightdata

# Hard cap on heal attempts per cycle. Two is deliberate: the demo needs exactly one re-prompt, and
# every further attempt is a real Scraper Studio heal costing real credits against an AI-Flow
# concurrency cap of 3 concurrent jobs. Enforced in the while condition, not by a break in the body.
MAX_HEAL_ATTEMPTS = 2

# WHAT THE FULL-PAGE VERIFICATION COSTS, stated where it is spent rather than in a design doc.
#
# Scraper Studio bills one credit per page load. Unchanged from before: one for the cycle's opening
# run, plus the heal job itself - whose preview rows AND template diff both arrive inside what that
# job already cost.
#
# ADDED: verifying one heal costs TWO more page loads, whichever way the verdict then goes.
#   +1  the draft run, `run(..., version="dev")`: the whole page as the healed template really
#       produces it. There is no cheaper way to get it. The gate shows two tiles of thirty, chosen
#       for us rather than sampled, and the checks that catch a swap are structurally blind at that
#       size - that is the measurement this whole module is built around.
#   +1  the production probe: one ordinary run, read back to prove that the draft approve did not
#       publish. Cheaper than being wrong about it once.
#
# So +2 per heal that reaches verification, and at most +4 per cycle because MAX_HEAL_ATTEMPTS is 2.
# A heal the pre-filter rejects costs +0: both runs happen strictly AFTER the gate has declined to
# reject, so a visibly broken heal never pays for a page it did not need.
PAGE_LOADS_TO_VERIFY_A_HEAL = 2

# Which check codes mean "this run came back broken enough to be worth healing". A degraded run is
# about missing data, not about values we disagree with - a drifted price is a real price.
_DEGRADATION_CODES = {"NULL_SPIKE", "FIELD_MISSING", "ROW_COUNT_SHIFT"}

SimulateHint = Union[str, Sequence[str], None]


# Where the rows a verdict was taken over actually came from. Recorded rather than inferred, because
# "we judged the whole page" and "we judged the first two tiles" are the difference this product
# sells, and a consumer must be able to read it off the record instead of trusting that the loop did
# the right thing.
ROWS_FROM_GATE = "gate_full_run"        # the gate itself handed over the whole population
ROWS_FROM_PREVIEW = "gate_preview"      # a preview: enough to reject on, never enough to price on
ROWS_FROM_FULL_RUN = "draft_full_run"   # run(version="dev") over the whole page - the only source
ROWS_FROM_NOTHING = "none"              # no rows were obtained at all

# What the probe after a draft approve found. See _probe_draft.
DRAFT_HELD = "held"            # production still serves the old template. Proven, this run.
DRAFT_PUBLISHED = "published"  # production already serves the healed one. The inference was WRONG.
DRAFT_MOOT = "moot"            # the heal changes nothing the probe can see, so there is nothing to
                               # prove: whether it published cannot matter.
DRAFT_UNPROVEN = "unproven"    # the probe could not establish either. Not a licence to publish.


@dataclass
class HealAttempt:
    """One trip through the approval gate. A cycle records every attempt, not just the last, so the
    event log can show the guardian's diagnosis turning into the next prompt.

    `verdict` is the verdict that DECIDED this attempt and `proposed_records` are the rows it was
    taken over - on the real gate, the full-page draft run rather than the preview. The two move
    together on purpose: every consumer (the event log, the counterfactual, the baseline ratchet)
    wants "what did we judge, and what did it say", and letting one of them describe the other's
    rows is how the old loop came to price off two tiles.
    """
    attempt: int                          # 1-based
    prompt: str                           # the prompt actually sent (attempt 2 is the sharpened one)
    verdict: Verdict
    proposed_records: list[dict]
    committed: bool                       # True iff this heal was confirmed and taken as our source
    # The cheap pre-filter's own verdict, over the gate's preview rows. None when the gate handed
    # over a full run and there was nothing to pre-filter. Kept apart from `verdict` because "the
    # preview objected" and "the whole page objected" are different claims, and only one of them
    # could ever have confirmed.
    gate_verdict: Optional[Verdict] = None
    preview_rows: int = 0
    rows_from: str = ROWS_FROM_GATE       # one of the ROWS_FROM_* constants above
    in_production: bool = False           # the healed template is what the collector now serves
    draft_probe: Optional[str] = None     # a DRAFT_* constant; None when no draft approve happened
    # The healer's own source diff, as evidence, whatever it said. Free at the gate, independent of
    # row count, and on a repoint it is the single most actionable sentence this product can put in
    # front of an operator. It never decides anything - see _publishable.
    template_diff: Optional[dict] = None
    notes: tuple[str, ...] = ()           # things that went wrong that were not the heal's fault


@dataclass
class ProposalDraft:
    """A reprice the seller will see. Not yet a row - service.py persists it."""
    current_price: float
    proposed_price: float
    reason: str
    status: str                           # "pending" | "held"
    confidence: int


@dataclass
class CycleOutcome:
    product_sku: str
    competitor_price: Optional[float]
    source_confirmed: bool
    verdict: Optional[Verdict]            # the FINAL attempt's verdict; None if no heal happened
    proposal: Optional[ProposalDraft]
    records: list[dict] = field(default_factory=list)      # the rows we ended up trusting
    trigger_reason: Optional[str] = None                   # None when no heal was needed
    heal_attempts: list[HealAttempt] = field(default_factory=list)
    counterfactual: Optional[dict] = None                  # populated only when a heal was rejected
    # Set only when a SAFETY MECHANISM, rather than a heal, turned out not to work. Today there is
    # exactly one: a draft approve that published. It is separate from `verdict` because the operator
    # response is different in kind - a bad heal is business as usual and this is not.
    control_alarm: Optional[str] = None

    @property
    def healed(self) -> bool:
        return bool(self.heal_attempts)


# --------------------------------------------------------------------------------------
# degradation gate
# --------------------------------------------------------------------------------------

def _degradation_reason(baseline: Baseline, baseline_profiles: dict[str, FieldProfile],
                        records: list[dict]) -> Optional[str]:
    """Why this run is worth healing, in the guardian's own words - or None if it looks fine.

    Returns the failing check's message so HealEvent.trigger_reason and the event log's `run:` line
    are a measured fact ("'price' is empty on 75% of rows") rather than a sentence someone typed.
    """
    if not records:
        return "The collector returned no rows at all."
    results = run_all_checks(baseline_profiles, records, baseline_count=baseline.record_count)
    for r in results:
        if not r.passed and r.code in _DEGRADATION_CODES:
            return r.message
    return None


# --------------------------------------------------------------------------------------
# the cycle
# --------------------------------------------------------------------------------------

def run_cycle_for_product(product: Product, baseline: Baseline, *,
                          simulate_run: Optional[str] = None,
                          simulate_heal: SimulateHint = None,
                          max_heal_attempts: int = MAX_HEAL_ATTEMPTS) -> CycleOutcome:
    """
    `product`       : a Product row (collector_id, competitor_url, my_price, cost, floor_margin)
    `baseline`      : a Baseline row (field_profiles + record_count) - the last-known-good reference
    `simulate_run`  : demo hook (mock only) - e.g. 'run_degraded' to trigger a heal on real nulls
    `simulate_heal` : demo hook (mock only) - a fixture key, or a per-attempt sequence of them
    """
    baseline_profiles = {k: FieldProfile.from_dict(v) for k, v in baseline.field_profiles.items()}

    records = brightdata.run(product.collector_id, product.competitor_url, _simulate=simulate_run)
    trigger_reason = _degradation_reason(baseline, baseline_profiles, records)

    # What production was serving BEFORE we touched anything. Kept because the draft probe needs a
    # "before" reading and this is one we have already paid for. It may well be the degraded run -
    # that is fine and in fact ideal: the question the probe asks is "did production change when we
    # approved", not "was production any good".
    pre_heal_records = records

    attempts: list[HealAttempt] = []
    source_confirmed = True
    verdict: Optional[Verdict] = None
    counterfactual: Optional[dict] = None
    control_alarm: Optional[str] = None

    if simulate_heal or trigger_reason:
        if trigger_reason is None:
            # A heal was forced for the demo without a measured degradation. Say so plainly rather
            # than printing a null-rate the code never measured.
            trigger_reason = "Heal triggered manually (simulated for demo)."

        prompt = _heal_prompt(product)
        attempt = 0
        while attempt < max_heal_attempts:
            attempt += 1
            proposal = brightdata.propose_heal(
                product.collector_id, prompt, product.competitor_url,
                capture_diff=True,
                _simulate=_simulate_for_attempt(simulate_heal, attempt),
            )
            record = _run_the_gate(product, baseline, baseline_profiles, proposal,
                                   attempt=attempt, prompt=prompt,
                                   pre_heal_records=pre_heal_records)
            attempts.append(record)
            verdict = record.verdict
            source_confirmed = record.committed

            if record.committed:
                # The ONLY assignment of `records` from a heal, and it can only be reached from a
                # verdict taken over a full run - see _run_the_gate. A preview never gets here.
                records = record.proposed_records

            if record.draft_probe == DRAFT_PUBLISHED:
                # The mechanism this loop stands on is not there. Re-prompting would spend another
                # heal against a collector we have just watched publish itself, so stop, and say
                # which of the two problems this is.
                control_alarm = _DRAFT_LEAK_ALARM
                break

            if record.committed or attempt >= max_heal_attempts:
                break

            # The guardian's own machine-readable diagnosis writes the next heal prompt.
            prompt = _resharpen_prompt(product, verdict)

    # The counterfactual describes the LAST REJECTED attempt: the number we refused to act on.
    #
    # Note what its rows may be. When the pre-filter rejected at the gate, they are the preview - two
    # tiles, possibly not even containing this product, in which case _extract_competitor_price
    # returns None and there is simply no counterfactual. That is correct and it is the one place a
    # preview is allowed to supply a number, because this number is explicitly the one we did NOT
    # act on. Nothing downstream may price from it.
    if not source_confirmed:
        rejected = next((a for a in reversed(attempts) if not a.committed), None)
        if rejected is not None:
            counterfactual = _counterfactual(
                product,
                _extract_competitor_price(product, rejected.proposed_records),
                source=f"rejected_heal_attempt_{rejected.attempt}",
            )

    competitor_price = _extract_competitor_price(product, records) if source_confirmed else None

    if not source_confirmed:
        draft = ProposalDraft(
            current_price=product.my_price,
            proposed_price=product.my_price,       # unchanged - we will not act on this
            reason=(verdict.brief if verdict else "Competitor source could not be confirmed."),
            status="held",
            confidence=(verdict.confidence if verdict else 0),
        )
    else:
        new_price, reason = engine.propose_price(product, competitor_price)
        draft = ProposalDraft(
            current_price=product.my_price,
            proposed_price=new_price,
            reason=reason,
            status="pending",
            confidence=(verdict.confidence if verdict else 100),
        )

    return CycleOutcome(
        product_sku=product.sku,
        competitor_price=competitor_price,
        source_confirmed=source_confirmed,
        verdict=verdict,
        proposal=draft,
        records=records,
        trigger_reason=trigger_reason,
        heal_attempts=attempts,
        counterfactual=counterfactual,
        control_alarm=control_alarm,
    )


# --------------------------------------------------------------------------------------
# the gate, and what a heal has to prove to get past it
# --------------------------------------------------------------------------------------

def _run_the_gate(product: Product, baseline: Baseline,
                  baseline_profiles: dict[str, FieldProfile],
                  proposal: brightdata.HealProposal, *,
                  attempt: int, prompt: str, pre_heal_records: list[dict]) -> HealAttempt:
    """Take one heal proposal from the approval gate to either production or the bin.

    This is the central claim of the product expressed as control flow, which is why it is one
    function rather than four spread through the cycle: a heal reaches production only after the
    healed template has run over the whole page and been judged on THAT run.

    The two exits that are not "publish" are both safe, and deliberately so. A rejection costs
    nothing but the heal we already paid for. A heal we could not finish verifying is HELD - the
    price stays exactly where it was - because the absence of evidence is not evidence, and the one
    thing this loop must never do is fill that absence with the preview.
    """
    diff = diff_templates(proposal.raw_diff)
    # Recorded whatever it says, but not when it says nothing: a NO_DIFF result means the gate
    # carried no source at all (every MOCK_MODE heal, and any caller that did not ask for it), and
    # storing "no template diff was returned" against every heal is the kind of always-empty field
    # operators learn to scroll past.
    diff_evidence = diff.to_dict() if diff.status is not ExtractionStatus.NO_DIFF else None

    gate = _verdict_over(baseline, baseline_profiles, proposal.proposed_records,
                         is_sample=proposal.is_sample, population_rows=proposal.population_rows)
    previewed = gate.evidence.is_partial

    def _record(verdict: Verdict, rows: list[dict], *, committed: bool, rows_from: str,
                in_production: bool = False, draft_probe: Optional[str] = None,
                notes: tuple[str, ...] = ()) -> HealAttempt:
        # Whether there was a preview at all is a property of the gate, not of the exit we took, so
        # it is decided once here. A gate that handed over the whole page has no pre-filter verdict
        # to report and no preview rows to count, and saying otherwise would put "2 preview rows" on
        # a heal that was shown thirty.
        return HealAttempt(attempt=attempt, prompt=prompt, verdict=verdict, proposed_records=rows,
                           committed=committed, gate_verdict=(gate if previewed else None),
                           preview_rows=(len(proposal.proposed_records) if previewed else 0),
                           rows_from=rows_from, in_production=in_production,
                           draft_probe=draft_probe, template_diff=diff_evidence, notes=notes)

    # A gate that showed the whole page is not a preview and there is nothing further to see.
    #
    # The real Bright Data gate never does this - it always elides, and `is_sample` stays True on
    # every gate payload for the reasons propose_heal argues. MOCK_MODE's fixture does, because it is
    # a full-size stand-in rather than a sample, and so would a real gate on a page short enough to
    # fit inside the preview. Branching on the EVIDENCE rather than on settings.mock_mode is what
    # keeps this file reading the same in a demo and in production, and it is the honest question in
    # both: did we see all of it?
    if gate.evidence.is_full:
        verdict = _with_source_note(_judge_if_ambiguous(gate, proposal.proposed_records), diff)
        if _publishable(verdict, diff, from_full_run=False):
            brightdata.approve_heal(product.collector_id, save_to_production=True)
            return _record(verdict, proposal.proposed_records, committed=True,
                           rows_from=ROWS_FROM_GATE, in_production=True)
        if not verdict.confirmed:
            brightdata.reject_heal(product.collector_id)
            return _record(verdict, proposal.proposed_records, committed=False,
                           rows_from=ROWS_FROM_GATE)
        # Confirmed on a complete gate, and yet the healer's own source says a field now reads a
        # different element. That buys one more page load and nothing else; fall through.

    # A PREVIEW CAN REJECT, BUT IT CAN NEVER CONFIRM.
    #
    # The pre-filter's whole job is to spend nothing further on a heal that is already visibly
    # wrong. The row-local checks are complete tests on a single row - a dropped field, a null
    # spike, a crossed-out original read as the sale price - so the gate catches those for free.
    # What it cannot do is clear anything, and this branch is the only one it has.
    elif gate.decision == FAIL:
        # Reject so the collector never sits at an open approval gate. Bright Data leaves the
        # scraper unchanged on reject, which is what makes a retry with a clearer prompt safe.
        brightdata.reject_heal(product.collector_id)
        return _record(_with_source_note(gate, diff), proposal.proposed_records, committed=False,
                       rows_from=ROWS_FROM_PREVIEW)

    # Accept into a DRAFT. Verified from @brightdata/cli v0.3.5 source: without --auto-save the
    # resume body is {message: true} and nothing asks for a save. INFERRED, and never confirmed
    # against the live API: that this therefore leaves production serving the old template. The
    # probe below is what turns that inference into a measurement, per run.
    brightdata.approve_heal(product.collector_id, save_to_production=False)

    try:
        full_rows = brightdata.run(product.collector_id, product.competitor_url, version="dev")
    except Exception as exc:                                    # noqa: BLE001 - argued below
        # The full run is the only evidence that could confirm, so failing to obtain it is not an
        # error to propagate - it is an answer. The source is unconfirmed and the price does not
        # move. A traceback here would throw away a correct and safe outcome that is already
        # available, and leave the caller with nothing at all to show.
        notes = _withdraw_after_draft(product.collector_id)
        return _record(_could_not_verify(f"the full-page run of the healed template failed ({exc})"),
                       [], committed=False, rows_from=ROWS_FROM_NOTHING,
                       notes=notes)

    probe, probe_notes = _probe_production(product, pre_heal_records, full_rows)

    verdict = _with_source_note(
        _judge_if_ambiguous(
            _verdict_over(baseline, baseline_profiles, full_rows,
                          is_sample=False, population_rows=None),
            full_rows),
        diff)

    if probe == DRAFT_PUBLISHED:
        # Loud, and safe. Loud because a safety mechanism, not a heal, is what failed. Safe because
        # the response is the same one the product already has for an unconfirmable source: hold,
        # and do not move the price. Deliberately NOT a raise - see _withdraw_after_draft.
        #
        # And deliberately no withdrawal either, unlike every other unhappy exit below. Rejecting
        # cannot un-publish what is already live, so the only thing it could do here is something
        # unpredictable to a collector that is currently serving customers. Leave it, and say so.
        return _record(_control_failed(verdict), full_rows, committed=False,
                       rows_from=ROWS_FROM_FULL_RUN, in_production=True,
                       draft_probe=probe, notes=probe_notes)

    if probe == DRAFT_UNPROVEN:
        # Unproven is not disproven, and it is not a licence either. Publishing here would be
        # exactly the assumption this probe exists to stop being an assumption.
        return _record(_could_not_prove_draft(verdict), full_rows, committed=False,
                       rows_from=ROWS_FROM_FULL_RUN, draft_probe=probe,
                       notes=probe_notes + _withdraw_after_draft(product.collector_id))

    if not _publishable(verdict, diff, from_full_run=True):
        return _record(verdict, full_rows, committed=False, rows_from=ROWS_FROM_FULL_RUN,
                       draft_probe=probe,
                       notes=probe_notes + _withdraw_after_draft(product.collector_id))

    brightdata.approve_heal(product.collector_id, save_to_production=True)
    return _record(verdict, full_rows, committed=True, rows_from=ROWS_FROM_FULL_RUN,
                   in_production=True, draft_probe=probe, notes=probe_notes)


def _publishable(verdict: Verdict, diff: TemplateDiff, *, from_full_run: bool) -> bool:
    """May this heal be written to production? Three conditions, and none of them is safe to drop.

    THE GUARDIAN CONFIRMED IT. Necessary, never sufficient.

    THE VERDICT SAW THE WHOLE POPULATION. `decide` already caps a partial-evidence verdict below
    PASS, so today this can never be the clause that fails - deliberately. That cap is a policy
    constant in the guardian; this is the line of code that spends money, and it must not be one
    edit to a threshold away from committing a delivery charge as a price. Stated here in its own
    terms so the property survives a change of mind next door.

    THE HEALER'S OWN SOURCE DOES NOT SAY A FIELD MOVED - unless we have already re-read the values
    over the whole page. This is the template diff as an ESCALATION and never as a judgement, and
    the study is why. The P1 heal reports has_swap=True and was CORRECT: the page genuinely swapped
    its elements and the healer adapted with a conditional on the label text, right on all 30 rows.
    That is structurally indistinguishable from being talked into a swap, which was wrong. So a
    repoint can buy exactly one more page load. It can never reject, and after the full run it has
    no vote at all - by then the values have answered the question the source could only raise.
    """
    if not verdict.confirmed or not verdict.evidence.is_full:
        return False
    return from_full_run or not diff.is_semantic


def _verdict_over(baseline: Baseline, baseline_profiles: dict[str, FieldProfile],
                  records: list[dict], *, is_sample: bool,
                  population_rows: Optional[int]) -> Verdict:
    """The battery and the roll-up in one call, so both halves of the evidence travel together."""
    return decide(run_all_checks(baseline_profiles, records,
                                 baseline_count=baseline.record_count,
                                 is_sample=is_sample, population_rows=population_rows))


def _judge_if_ambiguous(verdict: Verdict, records: list[dict]) -> Verdict:
    """Escalate to the Tier 3 semantic judge only when the cheap tiers could not decide.

    A clean PASS needs no second opinion and a CRITICAL FAIL has already been decided, so REVIEW is
    the only verdict worth spending an API call on. Outside MOCK_MODE with a key configured this is at
    most one call per held cycle; mocked, it is a no-op.

    Called on the DECIDING verdict only, never on a preview. Two reasons, and the second is the
    stronger. Every preview verdict is now a REVIEW by construction, so consulting here would mean
    an LLM call on every single heal, to produce an opinion that cannot change the outcome. And the
    judge reads the same two biased rows the checks read: a model reporting "these look like prices"
    about two delivery charges is precisely what the measured failure looks like from the inside.
    """
    if verdict.decision != REVIEW:
        return verdict
    return apply_judge(verdict, judge.judge_fields(records))


# --------------------------------------------------------------------------------------
# proving the draft assumption, once per approve
# --------------------------------------------------------------------------------------

# How far two runs' numbers may differ and still look like the output of the same template. Live
# pages move: a price drifts overnight, a card sells out, the catalogue reorders. A REPOINTED field
# does not drift, it jumps - the study's shipping-in-price heal moved the median by a factor of ~87.
# 2x sits far above the first and far below the second, which is the entire requirement.
_SAME_TEMPLATE_RATIO = 2.0

# Likewise for emptiness. A field going from always-present to mostly-empty is a selector that
# stopped matching, not a page having a quiet day.
_SAME_TEMPLATE_NULL_DELTA = 0.4

_DRAFT_LEAK_ALARM = (
    "Accepting a heal PUBLISHED it. `approve` without --auto-save was expected to leave production "
    "serving the previous template; production changed anyway. Until that is settled with Bright "
    "Data, treat every approve as a publish: Vouch cannot gate what it cannot hold back, so it will "
    "not move a price off this collector."
)


def _probe_production(product: Product, pre_heal_records: list[dict],
                      full_rows: list[dict]) -> tuple[str, tuple[str, ...]]:
    """Did accepting the heal leave production alone? Measured for THIS approve, not assumed.

    One ordinary run of the collector, read back and compared against two references we already
    hold: what production returned at the top of this cycle, and what the healed template returns.
    Production looking like the first and not the second is the inference holding. Production
    looking like the second is the inference being wrong, which is the case worth paying a page load
    to find out about, because the silent version of it publishes bad prices.
    """
    try:
        production_rows = brightdata.run(product.collector_id, product.competitor_url)
    except Exception as exc:                                    # noqa: BLE001
        return DRAFT_UNPROVEN, (f"could not read production back after approving: {exc}",)
    return _probe_draft(pre_heal_records, full_rows, production_rows), ()


def _probe_draft(pre_heal: list[dict], healed: list[dict], production: list[dict]) -> str:
    """Three-way comparison, in the order that keeps each answer honest.

    MOOT comes first. If the healed template extracts the same shape production already did, the two
    hypotheses are indistinguishable - and harmlessly so, because a template that changes nothing
    this comparison can see cannot move a price by publishing early. Reporting that as "held" would
    be claiming a measurement we did not make.
    """
    if _same_extraction(pre_heal, healed):
        return DRAFT_MOOT
    if _same_extraction(production, healed):
        return DRAFT_PUBLISHED
    if _same_extraction(production, pre_heal):
        return DRAFT_HELD
    # Production matches neither, so something moved that was not us - the page changed again
    # mid-cycle, most likely. Nothing here licenses a publish.
    return DRAFT_UNPROVEN


def _same_extraction(left: list[dict], right: list[dict]) -> bool:
    """Do these two runs look like the output of the SAME template?

    Deliberately not row equality. Two runs of one template minutes apart are never equal, so
    equality would report a template change on every comparison and the probe above would cry wolf
    until someone deleted it - and a safety check that always fires is a safety check that gets
    removed.

    What a repoint moves instead is the SHAPE of the extraction: which fields exist, what kind of
    value each holds, how often it is empty, and roughly how big it is. Those are stable under a
    page's own churn and violent under a selector change. Built on profile_run so it measures the
    same things the guardian measures rather than inventing a second vocabulary for them.

    KNOWN BLIND SPOT, and it is fine: two fields of the same type and similar magnitude trading
    places is invisible here, because `price` and `original_price` are 14% apart. This function is
    not a check. It answers one question - is production serving the healed template - and the
    guardian answers the other one, on the rows themselves, with the whole battery.
    """
    left_profiles, right_profiles = profile_run(left), profile_run(right)
    if set(left_profiles) != set(right_profiles):
        return False
    for name, a in left_profiles.items():
        b = right_profiles[name]
        if a.dtype != b.dtype:
            return False
        if abs(a.null_rate - b.null_rate) > _SAME_TEMPLATE_NULL_DELTA:
            return False
        if not _same_magnitude(a, b):
            return False
    return True


def _same_magnitude(a: FieldProfile, b: FieldProfile) -> bool:
    """Are two profiles' central values the same size, allowing for a page's own drift?

    Compared as a RATIO rather than bucketed. Buckets look tidy and are wrong at their edges: 999
    and 1001 land either side of an order-of-magnitude boundary, and reporting that as a changed
    template would hold a good heal for no reason.
    """
    if a.dtype == "numeric":
        x, y = a.median, b.median
    elif a.dtype == "string":
        x, y = a.mean_len, b.mean_len
    else:
        return True                     # a bool's true-rate is too volatile to carry this weight
    if x is None or y is None:
        # One side measurable and the other not is itself a difference: the field stopped parsing.
        return x is None and y is None
    x, y = abs(x), abs(y)
    if x == 0 or y == 0:
        return x == y
    return max(x, y) / min(x, y) <= _SAME_TEMPLATE_RATIO


def _withdraw_after_draft(collector_id: str) -> tuple[str, ...]:
    """Put the collector back to "no heal pending" after we have already answered its gate.

    Rejecting an OPEN gate is a known-good operation and the pre-filter above does exactly that.
    This is not that. The automation job has already been resumed with {message: true}, and what
    `scraper approve --reject` does to a job in that state is not something the CLI source settles.
    Attempted anyway, because the request it sends is {message: false}, and there is no reading of
    that which publishes anything: the worst case is a no-op.

    Contained, because by the time we are here production is untouched and the price is already
    held, so the only thing an exception could add is the loss of a correct answer. The currency
    guard in scraper/brightdata.py argues the opposite case at length and earns it by sitting
    upstream of every verdict; this sits after one, which is what makes the trade different.
    """
    try:
        brightdata.reject_heal(collector_id)
        return ()
    except Exception as exc:                                    # noqa: BLE001 - argued above
        return (f"could not withdraw the accepted heal; it remains in draft: {exc}",)


# --------------------------------------------------------------------------------------
# verdicts about the verification itself, rather than about the heal
# --------------------------------------------------------------------------------------

def _with_source_note(verdict: Verdict, diff: TemplateDiff) -> Verdict:
    """Put the healer's own account of what it changed in front of the operator.

    Only on a repoint, because that is the only case worth a human's attention: the study's
    healthy-page probe changed comments and a defensive numeric guard, and surfacing that as a
    change is how a warning channel teaches people to ignore it.

    Appended, never substituted. The guardian's finding is the decision; this is the explanation,
    and a brief that led with the explanation would read as if the source had decided.
    """
    if not diff.is_semantic or not diff.summary:
        return verdict
    return replace(verdict, brief=f"{verdict.brief} What the healer changed in the collector's own "
                                  f"source: {diff.summary}")


def _could_not_verify(reason: str) -> Verdict:
    """The verdict for a heal we never managed to run over the full page.

    Not a finding against the heal - an absence of evidence, which this product answers with a hold.
    Zero rows judged, stated as such, so nothing downstream can read the empty failure list as a
    clean bill of health.
    """
    return Verdict(
        decision=REVIEW, confidence=0,
        brief=(f"Couldn't confirm this heal: {reason}. The competitor price is left where it was, "
               f"because the only rows that could have settled it were never obtained."),
        failures=[], evidence=Evidence(rows_judged=0),
    )


def _could_not_prove_draft(verdict: Verdict) -> Verdict:
    """A full run we DID judge, held anyway because the publish could not be shown to be ours."""
    return replace(
        verdict,
        decision=(FAIL if verdict.decision == FAIL else REVIEW),
        # The ceiling the guardian uses for "an open question". Borrowed rather than re-invented:
        # what is missing here is not evidence about the rows, but it is the same kind of gap, and a
        # second number meaning the same thing is a number that drifts.
        confidence=min(verdict.confidence, PARTIAL_EVIDENCE_CEILING),
        brief=("Couldn't prove that accepting this heal left production untouched, so it was not "
               f"published and the price has not moved. {verdict.brief}"),
    )


def _control_failed(verdict: Verdict) -> Verdict:
    """The heal is live in production and nothing of ours gated it there.

    Held whatever the rows said. The values may well be fine - they are judged and reported either
    way, and the brief carries that judgement - but what failed is the mechanism that is supposed to
    make "verified before it ships" true, and continuing to move money through a control we have
    just measured as absent is the thing this product exists not to do. Holding costs one cycle. The
    alternative costs the claim.
    """
    return replace(
        verdict,
        decision=(FAIL if verdict.decision == FAIL else REVIEW),
        confidence=min(verdict.confidence, PARTIAL_EVIDENCE_CEILING),
        brief=f"{_DRAFT_LEAK_ALARM} The full-page verdict on the healed rows: {verdict.brief}",
    )


# --------------------------------------------------------------------------------------
# prompts
# --------------------------------------------------------------------------------------

def _heal_prompt(product: Product) -> str:
    return (f"The competitor page changed. Extract the current SALE price of the product "
            f"(not the crossed-out original, not shipping) matching SKU {product.sku}.")


def _resharpen_prompt(product: Product, verdict: Verdict) -> str:
    """Turn the guardian's diagnosis into a sharper instruction for the next heal.

    This is the whole point of validating before committing: we do not just refuse the bad fix, we
    tell Scraper Studio exactly what was wrong with it. Dict dispatch with a brief-based fallback,
    so an unrecognised check code can never raise mid-demo.
    """
    failure = verdict.primary_failure
    if failure is None:
        return _heal_prompt(product)

    ev = failure.evidence or {}
    field_name = ev.get("field", failure.field_name)
    base = ("Your previous fix was rejected by validation. ")

    if failure.code == "COLUMN_SWAP":
        other = ev.get("looks_like", "another column")
        own = ev.get("baseline_own_median")
        got = ev.get("proposed_median")
        detail = (
            f"The '{field_name}' field was reading the {str(other).upper()} value instead. "
            f"The values you returned (median {got}) match that column's historical range, not "
            f"'{field_name}''s (median about {own}). Re-extract '{field_name}' from the element "
            f"showing the item's own current sale price, and leave '{other}' as its own field. "
            f"Do not use the crossed-out original price."
        )
    elif failure.code == "VALUE_ORDER_INVERTED":
        upper = ev.get("upper", "the original price")
        detail = (
            f"The '{field_name}' field was reading the crossed-out {upper.replace('_', ' ').upper()} "
            f"instead of the discounted price: on {ev.get('inverted_rate', 0):.0%} of rows it came "
            f"back ABOVE '{upper}' (e.g. {ev.get('example_lower')} against "
            f"{ev.get('example_upper')}), which is impossible for a sale price. Extract the price "
            f"the customer actually pays today - the prominent one, not the struck-through reference "
            f"price beside it - and keep '{upper}' as its own separate field."
        )
    elif failure.code == "NUMERIC_DRIFT":
        detail = (
            f"The '{field_name}' values moved from a median of about "
            f"{ev.get('baseline_median')} to {ev.get('proposed_median')}. That is too large to be a "
            f"real price change - check whether the selector is matching a neighbouring element "
            f"such as a discount, a deposit, or a per-month figure."
        )
    elif failure.code == "NULL_SPIKE":
        detail = (
            f"The '{field_name}' field came back empty on most rows. The selector is probably "
            f"matching a container that is not present on every product card - find one that exists "
            f"on all of them."
        )
    elif failure.code == "FIELD_MISSING":
        detail = (
            f"The '{field_name}' field disappeared from the output entirely. It must still be "
            f"extracted, with the same name."
        )
    elif failure.code == "CARDINALITY_COLLAPSE":
        detail = (
            f"The '{field_name}' field returned nearly the same value on every row. It has probably "
            f"been pinned to a static element rather than read per product."
        )
    elif failure.code == "BOOL_RATIO_SHIFT":
        detail = (
            f"The '{field_name}' flag is now almost constant across rows. Read it per product "
            f"rather than from a page-level element."
        )
    else:
        detail = verdict.brief

    return f"{base}{detail} {_heal_prompt(product)}"


def _simulate_for_attempt(hint: SimulateHint, attempt: int) -> Optional[str]:
    """Which fixture a simulated heal should return on a given attempt.

    A scalar hint means "fail this way once, then the sharper prompt works" - which is the demo's
    resume beat. A sequence gives explicit per-attempt control, so a test can prove the retry cap
    holds when every attempt fails.
    """
    if hint is None:
        return None
    if isinstance(hint, str):
        return hint if attempt == 1 else "healed_good"
    if not hint:
        return None
    return hint[min(attempt - 1, len(hint) - 1)]


# --------------------------------------------------------------------------------------
# pricing helpers
# --------------------------------------------------------------------------------------

# A candidate must share at least this fraction of the product's own words to count as the same
# item. Set high on purpose: guessing wrong here means repricing against a DIFFERENT product, which is
# exactly the class of harm Vouch exists to prevent. Returning None is always the safer failure.
_MATCH_THRESHOLD = 0.6

# Words that carry no identifying signal in retail listing titles.
_NOISE_WORDS = frozenset({
    "the", "a", "an", "and", "or", "for", "with", "new", "sale", "hot", "pcs", "pack", "set",
    "women", "womens", "men", "mens", "girls", "boys", "plus", "size", "color", "colour",
})


def _normalise(text: str) -> str:
    """Case-fold, strip punctuation, and collapse whitespace."""
    lowered = str(text).strip().lower()
    kept = [ch if (ch.isalnum() or ch.isspace()) else " " for ch in lowered]
    return " ".join("".join(kept).split())


def _tokens(text: str) -> set[str]:
    return {w for w in _normalise(text).split() if w not in _NOISE_WORDS}


def _match_score(product_name: str, candidate: str) -> float:
    """How much of the product's identity the candidate accounts for.

    Deliberately asymmetric: the fraction of OUR product's tokens found in the candidate, not a
    symmetric Jaccard. Real listing titles are padded with marketing words and variant text, so a
    symmetric measure punishes a correct match just for being verbose.
    """
    ours = _tokens(product_name)
    if not ours:
        return 0.0
    theirs = _tokens(candidate)
    return len(ours & theirs) / len(ours)


def _extract_competitor_price(product: Product, records: list[dict],
                              price_field: str = "price") -> Optional[float]:
    """Find this product's row in the scraped set and pull its price.

    Three passes, most confident first. Exact-normalised matching alone is too brittle for real
    listing pages - live titles carry variant text, marketing prefixes and inconsistent punctuation
    that a seeded catalogue name will never reproduce character for character. But a loose match is
    worse than none: pricing against the wrong product is precisely the harm this product prevents.
    So the fuzzy pass must clear _MATCH_THRESHOLD and must be an unambiguous winner.
    """
    from app.guardian.checks import _coerce_number

    target = _normalise(product.name)
    if not target:
        return None

    # A row with no usable name is dropped outright. Keeping it would be actively dangerous: an empty
    # normalised name is a substring of EVERY product name, so the containment pass below would match
    # it against anything and hand back the price of an unidentified row.
    candidates = [(normalised, rec) for normalised, rec in
                  ((_normalise(rec.get("name", "")), rec) for rec in records) if normalised]
    if not candidates:
        return None

    # 1. exact, after normalisation
    for name, rec in candidates:
        if name == target:
            return _coerce_number(rec.get(price_field))

    # 2. one candidate contains our whole name (or vice versa) - common with variant suffixes
    contained = [rec for name, rec in candidates if target in name or name in target]
    if len(contained) == 1:
        return _coerce_number(contained[0].get(price_field))

    # 3. token overlap, but only when there is a clear single winner
    scored = sorted(((_match_score(product.name, name), rec) for name, rec in candidates),
                    key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] < _MATCH_THRESHOLD:
        return None
    if len(scored) > 1 and scored[1][0] >= scored[0][0]:
        return None          # a tie is not a match; refuse rather than pick arbitrarily
    return _coerce_number(scored[0][1].get(price_field))


def _margin_pct(price: Optional[float], cost: float) -> Optional[float]:
    if not price:
        return None
    return round((price - cost) / price, 6)


def _counterfactual(product: Product, bad_price: Optional[float], *, source: str) -> Optional[dict]:
    """What would have happened if we had trusted the rejected heal.

    Two numbers, deliberately, because they answer two different questions:

      applied_price - what OUR engine would have set. The floor rule clamps it, so this is usually
                      NOT the competitor's number. This is the honest figure, and it pre-empts the
                      obvious judge question "wouldn't your floor rule have caught this anyway?"
      naive_price   - what a repricer with no floor rule would have set. This is the catastrophe,
                      and it is the reason a floor rule alone is not a substitute for verifying
                      the number.

    The point being: a floor caps the disaster; only validating the data prevents the damage.

    `harm` names WHICH way this one hurts - see the branch below. The held card reads it, because
    "-165.98 per unit" and "+200.00 per unit" are both bad but for opposite reasons, and rendering the
    second one as if it were a margin loss would be simply wrong.
    """
    if bad_price is None:
        return None

    floor = round(product.cost * (1 + product.floor_margin), 2)
    applied, applied_reason = engine.propose_price(product, bad_price)
    naive = round(bad_price - 0.01, 2)
    delta = round(applied - product.my_price, 2)

    # A bad heal can hurt in two opposite directions, and conflating them would put a misleading
    # number on the held card. Reading the SHIPPING cost as the price pushes us down and destroys
    # margin. Reading the crossed-out ORIGINAL price pushes us up, where per-unit profit actually
    # rises - but we price ourselves above the market and lose the sale instead. Both are real harm;
    # only one of them is a margin story.
    if delta < 0:
        harm = "margin"
        harm_summary = (
            f"We would have cut our price to {applied:.2f}, giving up {abs(delta):.2f} of margin on "
            f"every unit sold."
        )
    elif delta > 0:
        harm = "competitiveness"
        harm_summary = (
            f"We would have raised our price to {applied:.2f}, putting us {delta:.2f} above where we "
            f"are today on a number we could not verify - pricing ourselves out of the sale rather "
            f"than losing margin on it."
        )
    else:
        harm = "none"
        harm_summary = "Acting on this would not have moved our price."

    return {
        "competitor_price": bad_price,
        "current_price": product.my_price,
        "floor_price": floor,
        "applied_price": applied,
        "applied_reason": applied_reason,
        "naive_price": naive,
        "margin_pct_now": _margin_pct(product.my_price, product.cost),
        "margin_pct_applied": _margin_pct(applied, product.cost),
        "margin_pct_naive": _margin_pct(naive, product.cost),
        "profit_per_unit_now": round(product.my_price - product.cost, 2),
        "profit_per_unit_applied": round(applied - product.cost, 2),
        "profit_per_unit_naive": round(naive - product.cost, 2),
        # the hero figure on the counterfactual panel: what acting on this would have cost per unit
        "profit_delta_vs_now": delta,
        "harm": harm,                  # "margin" | "competitiveness" | "none"
        "harm_summary": harm_summary,
        "source": source,
    }
