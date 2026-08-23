"""
The only module that writes rows.

orchestrator.py decides what happened; this file records it. Keeping the split strict is what lets
the cycle be tested with no database, and it means there is exactly one place to look when asking
"where did this row come from?".

Two policies here are load-bearing and easy to lose in a refactor:

  The trust ratchet. A Baseline advances ONLY on guardian-confirmed data - either the initial
  bootstrap or a heal that PASSed. Never on an ordinary run, because the degradation gate only
  screens for missing data; a run that slips past it has not faced the full battery and must not
  become the yardstick that the next heal is judged against. Since orchestrator.py started taking
  its confirming verdict over a full run of the healed template rather than over the approval
  gate's preview, `outcome.records` are the whole page - which is the first time the ratchet has
  advanced on a profile of thirty rows instead of two.

  No-op suppression. A proposal that would not move the price is not written at all. The queue is
  exception-based (README section 7): it exists to show the seller what needs judgment, not to list
  everything that is already fine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from sqlmodel import Session, select

from app.guardian.verdict import Verdict
from app.models import (
    Baseline,
    CompetitorObservation,
    HealEvent,
    HealStatus,
    HealVerdict,
    Product,
    ProposalStatus,
    RepriceProposal,
    _now,
)
from app.orchestrator import CycleOutcome, SimulateHint, run_cycle_for_product
from app.scraper import baseline as baseline_capture
from app.scraper import brightdata

# A proposal is "safe" to bulk-approve when the guardian was confident AND the move is small. 85
# mirrors verdict.py's PASS threshold deliberately: one number, one meaning, defined once.
CONFIDENCE_SAFE_FLOOR = 85
SAFE_DELTA_PCT = 0.15

# below this, a price change is not worth a human's attention
PRICE_EPSILON = 0.01


# --------------------------------------------------------------------------------------
# errors (mapped to HTTP status codes by the API layer, so this module stays FastAPI-free)
# --------------------------------------------------------------------------------------

class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, **detail):
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class Unprocessable(ServiceError):
    status_code = 422


# --------------------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------------------

@dataclass
class CycleRecord:
    product_id: int
    sku: str
    cycle_id: str
    outcome: CycleOutcome
    proposal_id: Optional[int] = None
    heal_event_ids: list[int] = field(default_factory=list)
    observation_id: Optional[int] = None
    baseline_refreshed: bool = False
    superseded_proposal_ids: list[int] = field(default_factory=list)


# The keys _event_evidence adds to a HealEvent's evidence dict, alongside the failing check's own.
#
# STRINGS AND BOOLEANS ONLY - no numbers, no nested objects. That is a hard constraint rather than a
# style preference. The held card renders this dict generically (frontend HeldCard.tsx,
# EvidencePanel): every numeric value goes through a currency formatter and everything else through
# String(), so `rows_judged: 30` reaches the screen as "$30.00" and a nested block as
# "[object Object]". A sentence survives that renderer unharmed, and a sentence is what an operator
# wanted from this panel anyway. Anything that needs the numbers machine-readable has POST /verify,
# which publishes rows_judged, full_battery and checks_stood_down as typed fields.
#
# Flat rather than namespaced for the same reason. Nothing collides today - every check's evidence
# keys name a field, a rate or a median - but a future check emitting `source_change` would silently
# overwrite this, so these names are kept sentence-like and unlike anything a check would produce.
VERIFICATION_KEYS = ("verified_on", "full_battery", "checks_stood_down", "gate_decision",
                     "draft_check", "source_change", "verification_note")

# How the record names each place the deciding rows can have come from. Spelled out rather than
# composed, because "the whole page" and "the first rows of it" are the distinction an operator is
# being asked to trust, and it must not reach them as a variable name.
_ROWS_FROM_TEXT = {
    "gate_full_run": "the approval gate returned the whole page — nothing further to run",
    "gate_preview": "the gate's preview only — enough to reject on, never enough to confirm",
    "draft_full_run": "a full run of the healed template, not the gate's preview",
    "none": "nothing — no rows were obtained, so there was nothing to verify",
}

_DRAFT_CHECK_TEXT = {
    "held": "production re-read after accepting: unchanged — the heal was still only a draft",
    "published": "production re-read after accepting: ALREADY CHANGED — accepting published it",
    "moot": "the healed template extracts the same shape production already did",
    "unproven": "production could not be shown unchanged after accepting — so nothing was published",
}


def _event_evidence(attempt) -> dict:
    """What one heal attempt leaves behind: the finding, and how hard we looked before deciding.

    The failing check's own evidence - {"looks_like": "shipping", the medians, ...} - is what lets
    the held card compose its sentence out of stored facts rather than hardcoded prose. The keys
    added on top of it are the other half, and they exist because the finding alone cannot tell the
    study's two answers apart: a PASS over two preview rows and a PASS over thirty write the
    identical row in this table without them, and the whole point of the loop that produced them is
    that they are not the same claim.
    """
    verdict = attempt.verdict
    failure = verdict.primary_failure
    evidence = dict(failure.evidence) if failure and failure.evidence else {}

    evidence["verified_on"] = _verified_on(attempt)
    evidence["full_battery"] = verdict.full_battery
    if verdict.checks_stood_down:
        evidence["checks_stood_down"] = ", ".join(verdict.checks_stood_down)
    if attempt.gate_verdict is not None:
        # Recorded apart from the deciding verdict, because "the preview objected" is a cheaper and
        # weaker claim than "the whole page objected", and reading the two as one is the confusion
        # this cycle was rebuilt to remove.
        evidence["gate_decision"] = (
            f"{attempt.gate_verdict.decision} on {attempt.preview_rows} preview row(s) — a preview "
            f"can reject, but it can never confirm")
    if attempt.draft_probe:
        evidence["draft_check"] = _DRAFT_CHECK_TEXT.get(attempt.draft_probe, attempt.draft_probe)

    diff = attempt.template_diff or {}
    if diff.get("semantic") and diff.get("summary"):
        # Only on a repoint. The study's healthy-page probe changed comments and a defensive numeric
        # guard, and recording that as a change is how a warning channel teaches people to skim.
        evidence["source_change"] = diff["summary"]
    if attempt.notes:
        evidence["verification_note"] = "; ".join(attempt.notes)

    return evidence


def _verified_on(attempt) -> str:
    """One sentence naming where the deciding rows came from, and how many of them there were."""
    provenance = attempt.verdict.evidence
    counted = ""
    if provenance.rows_judged is not None:
        counted = (f" ({provenance.rows_judged} of {provenance.population_rows} rows)"
                   if provenance.population_rows else f" ({provenance.rows_judged} rows)")
    return f"{_ROWS_FROM_TEXT.get(attempt.rows_from, attempt.rows_from)}{counted}"


def _supersede_open_holds(session: Session, product_id: int) -> list[int]:
    """Close any undecided HELD proposal for this product, because the source is confirmed now.

    Marked SUPERSEDED rather than REJECTED: the seller never declined it, the question simply stopped
    being open. Keeping the two distinct is what makes the decision log honest after a resume.
    """
    stale = list(session.exec(
        select(RepriceProposal)
        .where(RepriceProposal.product_id == product_id)
        .where(RepriceProposal.status == ProposalStatus.HELD)
        .where(RepriceProposal.decided_at == None)  # noqa: E711 - SQL NULL
    ))
    for proposal in stale:
        proposal.status = ProposalStatus.SUPERSEDED
        proposal.decided_at = _now()
        proposal.reason = f"{proposal.reason} [superseded: the source was confirmed on a later cycle]"
        session.add(proposal)
    return [p.id for p in stale]


@dataclass
class BulkResult:
    approved: list[int] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)   # [{id, why}] - why makes the button a product

    @property
    def applied_count(self) -> int:
        return len(self.approved)


# --------------------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------------------

def _baseline_for(session: Session, collector_id: str) -> Optional[Baseline]:
    return session.exec(
        select(Baseline).where(Baseline.collector_id == collector_id)
        .order_by(Baseline.captured_at.desc())
    ).first()


def ensure_baseline(session: Session, product: Product, *,
                    records: Optional[list[dict]] = None) -> Baseline:
    """The last-known-good profile for this product's collector, bootstrapping it if absent.

    Keyed on collector_id, not product: several SKUs are read from one competitor listing page, so
    they legitimately share one collector and therefore one baseline.
    """
    if not product.collector_id:
        raise Unprocessable(
            f"product {product.sku} has no collector_id - run the seeder or create a collector",
            sku=product.sku,
        )

    existing = _baseline_for(session, product.collector_id)
    if existing is not None:
        return existing

    if records is None:
        records = brightdata.run(product.collector_id, product.competitor_url)
    profiles, count = baseline_capture.capture(records)
    created = Baseline(collector_id=product.collector_id, record_count=count,
                       field_profiles=profiles)
    session.add(created)
    session.flush()
    return created


def refresh_baseline(session: Session, baseline: Baseline, records: list[dict]) -> Baseline:
    """Advance the yardstick. Only ever called for guardian-confirmed data - see the trust ratchet."""
    profiles, count = baseline_capture.capture(records)
    baseline.field_profiles = profiles
    baseline.record_count = count
    baseline.captured_at = _now()
    session.add(baseline)
    return baseline


# --------------------------------------------------------------------------------------
# the cycle
# --------------------------------------------------------------------------------------

def run_cycle(session: Session, product: Product, *,
              simulate_run: Optional[str] = None,
              simulate_heal: SimulateHint = None,
              max_heal_attempts: Optional[int] = None) -> CycleRecord:
    """Run one product's cycle and persist everything it produced.

    Exactly one commit, at the end. If anything raises part-way there is no half-written cycle to
    explain - the database still holds the previous, coherent state.
    """
    baseline = ensure_baseline(session, product)
    cycle_id = uuid.uuid4().hex[:8]

    kwargs = {}
    if max_heal_attempts is not None:
        kwargs["max_heal_attempts"] = max_heal_attempts
    outcome = run_cycle_for_product(product, baseline, simulate_run=simulate_run,
                                    simulate_heal=simulate_heal, **kwargs)

    record = CycleRecord(product_id=product.id, sku=product.sku, cycle_id=cycle_id, outcome=outcome)

    # --- one HealEvent per attempt --------------------------------------------------------
    for attempt in outcome.heal_attempts:
        verdict = attempt.verdict
        failure = verdict.primary_failure
        event = HealEvent(
            collector_id=product.collector_id,
            product_id=product.id,
            trigger_reason=outcome.trigger_reason or "",
            prompt=attempt.prompt,
            proposed_confidence=verdict.confidence,
            verdict=HealVerdict(verdict.decision),
            risk_brief=verdict.brief,
            status=HealStatus.APPROVED if attempt.committed else HealStatus.REJECTED,
            primary_check_code=failure.code if failure else None,
            evidence=_event_evidence(attempt),
            attempt=attempt.attempt,
            cycle_id=cycle_id,
        )
        session.add(event)
        session.flush()
        record.heal_event_ids.append(event.id)

    # --- the baseline ratchet -------------------------------------------------------------
    if outcome.source_confirmed and any(a.committed for a in outcome.heal_attempts):
        refresh_baseline(session, baseline, outcome.records)
        record.baseline_refreshed = True

    # --- what we observed, confirmed or not ----------------------------------------------
    observed_price = outcome.competitor_price
    if not outcome.source_confirmed and outcome.counterfactual:
        # The number we refused to act on. Stored as an unconfirmed observation so the price chart
        # shows an honest gap and the staleness clock stops - NOT as the counterfactual itself.
        observed_price = outcome.counterfactual.get("competitor_price")

    observation = CompetitorObservation(
        product_id=product.id,
        observed_price=observed_price,
        source_url=product.competitor_url,
        run_id=cycle_id,
        confirmed=outcome.source_confirmed,
    )
    session.add(observation)
    session.flush()
    record.observation_id = observation.id

    # --- retire holds this cycle has answered ---------------------------------------------
    # A hold means "we could not confirm this source". Once a later cycle DOES confirm it, that hold
    # is stale, and leaving it in the queue means the held card never clears after the re-prompt
    # succeeds - the guardian would look like it never changes its mind.
    if outcome.source_confirmed:
        record.superseded_proposal_ids = _supersede_open_holds(session, product.id)

    # --- the proposal ---------------------------------------------------------------------
    draft = outcome.proposal
    if draft is not None:
        is_noop = abs(draft.proposed_price - draft.current_price) < PRICE_EPSILON
        if draft.status == "held" or not is_noop:
            proposal = RepriceProposal(
                product_id=product.id,
                current_price=draft.current_price,
                proposed_price=draft.proposed_price,
                reason=draft.reason,
                status=ProposalStatus(draft.status),
                confidence=draft.confidence,
                heal_event_id=record.heal_event_ids[-1] if record.heal_event_ids else None,
                counterfactual=outcome.counterfactual,
            )
            session.add(proposal)
            session.flush()
            record.proposal_id = proposal.id

    session.commit()
    return record


def run_all_cycles(session: Session, *, skus: Optional[Iterable[str]] = None,
                   simulate_run: Optional[str] = None,
                   simulate_heal: SimulateHint = None,
                   max_heal_attempts: Optional[int] = None) -> list[CycleRecord]:
    """Run every product's cycle, one at a time.

    Deliberately serial. Bright Data caps concurrent AI-Flow jobs (create/heal) at 3 per account, and
    a 4th returns 429; fanning out here would spend the demo in exponential backoff.
    """
    query = select(Product)
    if skus is not None:
        skus = list(skus)
        query = query.where(Product.sku.in_(skus))
    products = list(session.exec(query))

    if skus is not None:
        missing = set(skus) - {p.sku for p in products}
        if missing:
            raise NotFound(f"unknown sku(s): {', '.join(sorted(missing))}")

    return [run_cycle(session, p, simulate_run=simulate_run, simulate_heal=simulate_heal,
                      max_heal_attempts=max_heal_attempts)
            for p in products]


# --------------------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------------------

def _load_proposal(session: Session, proposal_id: int) -> RepriceProposal:
    proposal = session.get(RepriceProposal, proposal_id)
    if proposal is None:
        raise NotFound(f"proposal {proposal_id} not found")
    return proposal


def _price_to_apply(proposal: RepriceProposal) -> float:
    """What approving this proposal actually sets the price to.

    A held proposal never moves the price, so proposed_price == current_price. Overriding a hold
    therefore means applying what the pricing engine WOULD have set - which is the counterfactual's
    floor-clamped figure, already computed at cycle time.
    """
    if proposal.status != ProposalStatus.HELD:
        return proposal.proposed_price

    counterfactual = proposal.counterfactual or {}
    applied = counterfactual.get("applied_price")
    if applied is None:
        raise Unprocessable("nothing to apply - this hold has no proposed price",
                            proposal_id=proposal.id)
    return float(applied)


def approve_proposal(session: Session, proposal_id: int, *, force: bool = False) -> RepriceProposal:
    proposal = _load_proposal(session, proposal_id)

    if proposal.decided_at is not None:
        # Idempotency guard: a double-click on stage must not apply a change twice.
        raise Conflict(f"proposal {proposal_id} was already {proposal.status.value}",
                       status=proposal.status.value)

    if proposal.status == ProposalStatus.HELD and not force:
        # This refusal IS the product. You cannot accidentally approve a change the guardian held.
        raise Conflict(
            "proposal is held by the guardian; pass force=true to override",
            proposal_id=proposal.id,
            confidence=proposal.confidence,
            check_code=_check_code_for(session, proposal),
        )

    product = session.get(Product, proposal.product_id)
    if product is None:
        raise NotFound(f"product {proposal.product_id} not found")

    applied = _price_to_apply(proposal)

    # Defence in depth. The engine already clamps and the counterfactual's applied_price IS the
    # floor, so both legitimate paths pass; this stops a future caller from routing around them.
    floor = round(product.cost * (1 + product.floor_margin), 2)
    if applied < floor:
        raise Unprocessable(
            f"refusing to set {applied} below the floor price {floor}",
            applied=applied, floor=floor,
        )

    proposal.status = ProposalStatus.APPROVED
    proposal.decided_at = _now()
    product.my_price = applied
    product.updated_at = _now()
    session.add(proposal)
    session.add(product)
    session.commit()
    session.refresh(proposal)
    return proposal


def reject_proposal(session: Session, proposal_id: int, *,
                    note: Optional[str] = None) -> RepriceProposal:
    """Also backs the held card's [Skip this cycle] - skipping is rejecting with a note."""
    proposal = _load_proposal(session, proposal_id)
    if proposal.decided_at is not None:
        raise Conflict(f"proposal {proposal_id} was already {proposal.status.value}",
                       status=proposal.status.value)

    proposal.status = ProposalStatus.REJECTED
    proposal.decided_at = _now()
    if note:
        proposal.reason = f"{proposal.reason} [{note}]"
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal


def is_safe(proposal: RepriceProposal, product: Product, *,
            min_confidence: int = CONFIDENCE_SAFE_FLOOR,
            max_delta_pct: float = SAFE_DELTA_PCT) -> tuple[bool, Optional[str]]:
    """Whether a proposal qualifies for one-click bulk approval, and if not, why not.

    Returned as a reason rather than a bare bool so the UI can explain every skip - that is what
    makes "Approve all safe changes" feel like a product instead of a bulk UPDATE.
    """
    if proposal.status != ProposalStatus.PENDING:
        return False, f"not pending (is {proposal.status.value})"
    if proposal.confidence < min_confidence:
        return False, f"confidence {proposal.confidence} is below {min_confidence}"
    if not proposal.current_price:
        return False, "no current price to compare against"
    delta_pct = abs(proposal.proposed_price - proposal.current_price) / proposal.current_price
    if delta_pct > max_delta_pct:
        return False, f"moves the price {delta_pct:.1%}, over the {max_delta_pct:.0%} safe band"
    floor = round(product.cost * (1 + product.floor_margin), 2)
    if proposal.proposed_price < floor:
        return False, f"would fall below the floor price {floor:.2f}"
    return True, None


def approve_all_safe(session: Session, *, min_confidence: int = CONFIDENCE_SAFE_FLOOR,
                     max_delta_pct: float = SAFE_DELTA_PCT) -> BulkResult:
    result = BulkResult()
    proposals = list(session.exec(
        select(RepriceProposal).where(RepriceProposal.status == ProposalStatus.PENDING)
        .order_by(RepriceProposal.created_at)
    ))

    for proposal in proposals:
        product = session.get(Product, proposal.product_id)
        if product is None:
            result.skipped.append({"id": proposal.id, "why": "product missing"})
            continue
        ok, why = is_safe(proposal, product, min_confidence=min_confidence,
                          max_delta_pct=max_delta_pct)
        if not ok:
            result.skipped.append({"id": proposal.id, "why": why})
            continue
        # Same code path as a single approval, so the floor guard cannot be bypassed in bulk.
        approve_proposal(session, proposal.id)
        result.approved.append(proposal.id)

    return result


# --------------------------------------------------------------------------------------
# reads the UI needs
# --------------------------------------------------------------------------------------

def last_confirmed_observation(session: Session, product_id: int) -> Optional[CompetitorObservation]:
    """The newest observation the guardian stood behind.

    Every read of "the current competitor price" must come through here. Unconfirmed observations are
    deliberately kept in the table for the chart gap, so a query missing `confirmed == True` would
    happily show the price of a heal we rejected.
    """
    return session.exec(
        select(CompetitorObservation)
        .where(CompetitorObservation.product_id == product_id)
        .where(CompetitorObservation.confirmed == True)  # noqa: E712 - SQL, not Python truthiness
        .order_by(CompetitorObservation.created_at.desc(), CompetitorObservation.id.desc())
    ).first()


def staleness_label(ts: Optional[datetime]) -> str:
    """"last confirmed 2h ago", computed server-side.

    models._now() is naive UTC; letting a browser parse it as local time puts a multi-hour error on
    this label. The frontend must do no date arithmetic at all.
    """
    if ts is None:
        return "never confirmed"
    seconds = (_now() - ts).total_seconds()
    if seconds < 0:
        return "last confirmed just now"
    if seconds < 90:
        return "last confirmed just now"
    minutes = seconds / 60
    if minutes < 90:
        return f"last confirmed {int(minutes)}m ago"
    hours = minutes / 60
    if hours < 36:
        return f"last confirmed {int(hours)}h ago"
    return f"last confirmed {int(hours / 24)}d ago"


def _check_code_for(session: Session, proposal: RepriceProposal) -> Optional[str]:
    if proposal.heal_event_id is None:
        return None
    event = session.get(HealEvent, proposal.heal_event_id)
    return event.primary_check_code if event else None


def heal_log_entries(event: HealEvent) -> list[dict]:
    """Expand one HealEvent into the operator log, in real Scraper Studio vocabulary.

    Done server-side so the vocabulary lives in exactly one reviewable place, and so `kind` gives the
    frontend its severity colour without parsing prose.

    The middle of this log is the part that changed. It used to read gate -> verdict -> commit, which
    was an accurate description of a loop that judged the approval gate's preview and committed on
    it. It now shows what the preview could and could not settle, and then the full-page run the
    decision was actually taken over, because those two steps are the product and a log that skipped
    them would describe a cheaper thing than the one that ran.
    """
    entries: list[dict] = []
    evidence = event.evidence or {}

    if event.attempt == 1:
        if event.trigger_reason:
            entries.append({"kind": "run", "text": f"run: {event.trigger_reason}"})
    else:
        entries.append({
            "kind": "reprompt",
            "text": f"heal re-prompted with the guardian's diagnosis (attempt {event.attempt})",
        })

    entries.append({"kind": "heal", "text": "heal proposed — awaiting approval"})
    entries.extend(_verification_entries(evidence))

    if event.verdict == HealVerdict.PASS:
        entries.append({
            "kind": "verdict",
            "text": f"verdict: passed — meaning preserved · "
                    f"confidence {event.proposed_confidence}/100",
        })
    elif event.verdict is not None:
        tag = f" · {event.primary_check_code}" if event.primary_check_code else ""
        entries.append({
            "kind": "verdict",
            "text": f"verdict: {event.verdict.value}ed — {event.risk_brief}{tag} · "
                    f"confidence {event.proposed_confidence}/100",
        })

    if event.status == HealStatus.APPROVED:
        entries.append({"kind": "commit", "text": "fix approved and saved to production"})
    elif event.status == HealStatus.REJECTED:
        entries.append({"kind": "commit", "text": "fix rejected — previous collector retained"})

    return entries


def _verification_entries(evidence: dict) -> list[dict]:
    """The steps between the gate and the verdict, in the order they happened.

    Reads the sentences _event_evidence already stored rather than recomposing them, so the log and
    the held card's evidence panel cannot end up describing the same heal differently. Silently
    empty for an event written before any of this existed: an absent key means we do not know how
    hard anyone looked, and printing a reassuring line for that is worse than printing nothing.

    NO NEW `kind` VALUES. The five are a published contract - frontend/src/types.ts declares them as
    a closed union and the receipt draws a glyph per kind, so a sixth ships as a blank circle in the
    one place these lines are read. New steps therefore reuse the closest existing kind: reading a
    page is a `run` whoever asked for it, and a judgement about the preview is a `verdict` even
    though it is not the final one. Widening the union is a frontend change, not a reason to ship a
    broken glyph.
    """
    lines = (
        ("source_change", "heal", "source diff: {}"),
        ("gate_decision", "verdict", "pre-filter: {}"),
        ("verified_on", "run", "verdict taken over {}"),
        ("draft_check", "run", "{}"),
        ("verification_note", "commit", "{}"),
    )
    return [{"kind": kind, "text": template.format(evidence[key])}
            for key, kind, template in lines if evidence.get(key)]
