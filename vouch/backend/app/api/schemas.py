"""
Read models for the dashboard, plus the builders that assemble them.

Every shape the frontend consumes is defined here, so `frontend/src/types.ts` has exactly one file to
mirror and FastAPI can publish an accurate OpenAPI schema.

Two conventions the whole API follows:

  Timestamps ship twice - once as ISO-8601 for machines, once as a prebuilt human label. models._now()
  is naive UTC, so a browser parsing it as local time would put a multi-hour error on "last confirmed
  2h ago". The frontend performs no date arithmetic at all.

  Derived money is computed here, never in the client. Margins, deltas and floor prices come off the
  same pricing rules the engine uses, so the UI can never disagree with what Vouch would actually do.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from app import service
from app.models import HealEvent, Product, ProposalStatus, RepriceProposal


# --------------------------------------------------------------------------------------
# products
# --------------------------------------------------------------------------------------

class ProductRef(BaseModel):
    id: int
    sku: str
    name: str


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    my_price: float
    cost: float
    floor_margin: float
    floor_price: float
    margin_pct: Optional[float]
    competitor_url: str
    collector_id: Optional[str]
    last_confirmed_price: Optional[float]
    last_confirmed_at: Optional[datetime]
    last_confirmed_label: str
    source_confirmed: bool
    held_proposal_id: Optional[int]
    updated_at: datetime


def floor_price(product: Product) -> float:
    return round(product.cost * (1 + product.floor_margin), 2)


def margin_pct(price: Optional[float], cost: float) -> Optional[float]:
    if not price:
        return None
    return round((price - cost) / price, 6)


def build_product(session: Session, product: Product) -> ProductOut:
    latest = service.last_confirmed_observation(session, product.id)
    held = session.exec(
        select(RepriceProposal)
        .where(RepriceProposal.product_id == product.id)
        .where(RepriceProposal.status == ProposalStatus.HELD)
        .where(RepriceProposal.decided_at == None)  # noqa: E711 - SQL NULL, not Python None
        .order_by(RepriceProposal.created_at.desc())
    ).first()

    return ProductOut(
        id=product.id, sku=product.sku, name=product.name,
        my_price=product.my_price, cost=product.cost, floor_margin=product.floor_margin,
        floor_price=floor_price(product),
        margin_pct=margin_pct(product.my_price, product.cost),
        competitor_url=product.competitor_url, collector_id=product.collector_id,
        last_confirmed_price=latest.observed_price if latest else None,
        last_confirmed_at=latest.created_at if latest else None,
        last_confirmed_label=service.staleness_label(latest.created_at if latest else None),
        source_confirmed=held is None,
        held_proposal_id=held.id if held else None,
        updated_at=product.updated_at,
    )


# --------------------------------------------------------------------------------------
# proposals
# --------------------------------------------------------------------------------------

class SourceOut(BaseModel):
    url: str
    confirmed: bool
    observed_price: Optional[float]
    last_confirmed_at: Optional[datetime]
    last_confirmed_label: str


class GuardianOut(BaseModel):
    """What the guardian found, for the held card. `check_code` and `evidence` are read straight off
    the HealEvent rather than re-derived, so the card's sentence is composed from stored facts."""
    heal_event_id: int
    collector_id: str
    verdict: Optional[str]
    confidence: int
    check_code: Optional[str]
    brief: str
    evidence: dict
    attempt: int
    attempts_total: int
    prompt: str


class ProposalOut(BaseModel):
    id: int
    status: str
    confidence: int
    current_price: float
    proposed_price: float
    delta: float
    delta_pct: Optional[float]
    reason: str
    created_at: datetime
    created_label: str
    decided_at: Optional[datetime]
    floor_price: float
    margin_pct_now: Optional[float]
    margin_pct_after: Optional[float]
    is_safe: bool
    safe_reason: Optional[str]
    product: ProductRef
    source: SourceOut
    guardian: Optional[GuardianOut]
    counterfactual: Optional[dict]


def _observation_for(session: Session, proposal: RepriceProposal):
    """The observation this proposal was built from, confirmed or not.

    A held proposal's own cycle wrote an UNCONFIRMED observation, and that row is what carries the
    row-level bad price the card quotes ("the healed price ($19.99)"). The check's evidence only has
    a median, so this lookup is not redundant with it.
    """
    from app.models import CompetitorObservation

    return session.exec(
        select(CompetitorObservation)
        .where(CompetitorObservation.product_id == proposal.product_id)
        .where(CompetitorObservation.created_at <= proposal.created_at)
        .order_by(CompetitorObservation.created_at.desc(), CompetitorObservation.id.desc())
    ).first()


def build_proposal(session: Session, proposal: RepriceProposal) -> ProposalOut:
    product = session.get(Product, proposal.product_id)
    latest_confirmed = service.last_confirmed_observation(session, proposal.product_id)
    observation = _observation_for(session, proposal)

    guardian = None
    if proposal.heal_event_id is not None:
        event = session.get(HealEvent, proposal.heal_event_id)
        if event is not None:
            attempts_total = len(list(session.exec(
                select(HealEvent).where(HealEvent.cycle_id == event.cycle_id)
            ))) if event.cycle_id else event.attempt
            guardian = GuardianOut(
                heal_event_id=event.id,
                collector_id=event.collector_id,
                verdict=event.verdict.value if event.verdict else None,
                confidence=event.proposed_confidence,
                check_code=event.primary_check_code,
                brief=event.risk_brief,
                evidence=event.evidence or {},
                attempt=event.attempt,
                attempts_total=attempts_total,
                prompt=event.prompt,
            )

    delta = round(proposal.proposed_price - proposal.current_price, 2)
    safe, why = service.is_safe(proposal, product) if product else (False, "product missing")

    return ProposalOut(
        id=proposal.id,
        status=proposal.status.value,
        confidence=proposal.confidence,
        current_price=proposal.current_price,
        proposed_price=proposal.proposed_price,
        delta=delta,
        delta_pct=(round(delta / proposal.current_price, 6) if proposal.current_price else None),
        reason=proposal.reason,
        created_at=proposal.created_at,
        created_label=service.staleness_label(proposal.created_at).replace("last confirmed ", ""),
        decided_at=proposal.decided_at,
        floor_price=floor_price(product) if product else 0.0,
        margin_pct_now=margin_pct(proposal.current_price, product.cost) if product else None,
        margin_pct_after=margin_pct(proposal.proposed_price, product.cost) if product else None,
        is_safe=safe,
        safe_reason=why,
        product=ProductRef(id=product.id, sku=product.sku, name=product.name),
        source=SourceOut(
            url=product.competitor_url,
            confirmed=bool(observation.confirmed) if observation else False,
            observed_price=observation.observed_price if observation else None,
            last_confirmed_at=latest_confirmed.created_at if latest_confirmed else None,
            last_confirmed_label=service.staleness_label(
                latest_confirmed.created_at if latest_confirmed else None),
        ),
        guardian=guardian,
        counterfactual=proposal.counterfactual,
    )


# --------------------------------------------------------------------------------------
# heal events
# --------------------------------------------------------------------------------------

class LogEntry(BaseModel):
    kind: str          # run | heal | verdict | commit | reprompt - drives the row's colour
    text: str


class HealEventOut(BaseModel):
    id: int
    cycle_id: Optional[str]
    collector_id: str
    attempt: int
    verdict: Optional[str]
    proposed_confidence: int
    primary_check_code: Optional[str]
    risk_brief: str
    prompt: str
    trigger_reason: str
    status: str
    created_at: datetime
    created_label: str
    product: Optional[ProductRef]
    entries: list[LogEntry]


def build_heal_event(session: Session, event: HealEvent) -> HealEventOut:
    product = session.get(Product, event.product_id) if event.product_id else None
    return HealEventOut(
        id=event.id, cycle_id=event.cycle_id, collector_id=event.collector_id,
        attempt=event.attempt,
        verdict=event.verdict.value if event.verdict else None,
        proposed_confidence=event.proposed_confidence,
        primary_check_code=event.primary_check_code,
        risk_brief=event.risk_brief, prompt=event.prompt,
        trigger_reason=event.trigger_reason, status=event.status.value,
        created_at=event.created_at,
        created_label=service.staleness_label(event.created_at).replace("last confirmed ", ""),
        product=(ProductRef(id=product.id, sku=product.sku, name=product.name)
                 if product else None),
        entries=[LogEntry(**e) for e in service.heal_log_entries(event)],
    )


# --------------------------------------------------------------------------------------
# cycles
# --------------------------------------------------------------------------------------

class CycleRunRequest(BaseModel):
    skus: Optional[list[str]] = None
    simulate_run: Optional[str] = None
    simulate_heal: Optional[object] = None      # str | list[str]; validated in the route
    max_attempts: Optional[int] = None


class CycleSummary(BaseModel):
    sku: str
    cycle_id: str
    source_confirmed: bool
    competitor_price: Optional[float]
    trigger_reason: Optional[str]
    proposal_id: Optional[int]
    proposal_status: Optional[str]
    confidence: Optional[int]
    heal_event_ids: list[int]
    attempts: int
    baseline_refreshed: bool
    superseded_proposal_ids: list[int]


class CycleRunResponse(BaseModel):
    mock_mode: bool
    simulate_requested: Optional[object]
    simulate_applied: Optional[object]
    warnings: list[str]
    cycles: list[CycleSummary]


def build_cycle_summary(record: service.CycleRecord) -> CycleSummary:
    outcome = record.outcome
    return CycleSummary(
        sku=record.sku, cycle_id=record.cycle_id,
        source_confirmed=outcome.source_confirmed,
        competitor_price=outcome.competitor_price,
        trigger_reason=outcome.trigger_reason,
        proposal_id=record.proposal_id,
        proposal_status=(outcome.proposal.status if outcome.proposal else None),
        confidence=(outcome.verdict.confidence if outcome.verdict else None),
        heal_event_ids=record.heal_event_ids,
        attempts=len(outcome.heal_attempts),
        baseline_refreshed=record.baseline_refreshed,
        superseded_proposal_ids=record.superseded_proposal_ids,
    )


# --------------------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------------------

class ApproveResponse(BaseModel):
    """Returns the updated rows so the UI repaints from server truth instead of guessing."""
    proposal: ProposalOut
    product: ProductOut
    applied_price: float


class BulkApproveRequest(BaseModel):
    min_confidence: int = service.CONFIDENCE_SAFE_FLOOR
    max_delta_pct: float = service.SAFE_DELTA_PCT


class BulkApproveResponse(BaseModel):
    approved: list[int]
    applied_count: int
    skipped: list[dict]
    products: list[ProductOut]


# --------------------------------------------------------------------------------------
# history (the honest chart)
# --------------------------------------------------------------------------------------

class HistoryPoint(BaseModel):
    ts: datetime
    ts_label: str
    my_price: float
    competitor_price: Optional[float]   # None on an unconfirmed cycle - the gap lives in the DATA,
    confirmed: bool                     # so no renderer can accidentally interpolate across it


class HistoryOut(BaseModel):
    product: ProductRef
    points: list[HistoryPoint]
    counterfactual: Optional[dict]
    last_confirmed_label: str


# --------------------------------------------------------------------------------------
# trust layer - the stateless /verify surface
# --------------------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    """A caller hands us the rows to judge and a reference to judge them against.

    The reference comes one of two ways, and exactly one must be given (validated in the route):
    `baseline_records` are raw last-known-good rows we profile server-side, and `baseline_profiles`
    are profiles the caller already computed (e.g. read off a stored Baseline). Everything else is
    optional and mirrors the knobs the internal guardian already exposes.
    """
    candidate_records: list[dict]                          # REQUIRED, non-empty - the rows to judge
    baseline_records: Optional[list[dict]] = None          # raw reference rows, profiled here
    baseline_profiles: Optional[dict[str, dict]] = None    # precomputed serialized FieldProfiles
    baseline_count: Optional[int] = None                   # inferred from baseline_records if omitted
    is_sample: bool = False                                 # candidate is a preview - suppress volume
    use_judge: bool = False                                 # allow Tier 3 (no-op in mock / no key)


class VerifyFailure(BaseModel):
    """One failed check, flattened from a guardian CheckResult for the wire."""
    code: str
    severity: str
    field: str
    message: str
    evidence: dict


class VerifyResponse(BaseModel):
    decision: str                 # pass | review | fail
    confirmed: bool               # decision == pass
    confidence: int               # 0-100
    brief: str
    failures: list[VerifyFailure]
    judge_consulted: bool


# --------------------------------------------------------------------------------------
# demo capabilities
# --------------------------------------------------------------------------------------

class DemoHintOut(BaseModel):
    """One scenario the active dataset can replay, as a control the dashboard can render."""
    key: str                  # the fixture key, sent back as simulate_run / simulate_heal
    label: str                # what the button says
    detail: str               # the tooltip: what this scenario is and which check catches it
    stage: str                # "run" (feeds simulate_run) | "heal" (feeds simulate_heal)


class DemoHintsOut(BaseModel):
    """What the dashboard's demo controls are allowed to offer right now.

    The available scenarios depend on which dataset MOCK_MODE is replaying: the dataset derived from
    the live collector carries no `original_price`, because the collector never captured one, so the
    value-ordering scenario genuinely cannot be replayed against it. Advertising a control the data
    cannot honour would be a small lie in exactly the place this product claims not to tell one.
    """
    mock_mode: bool
    dataset: str
    dataset_note: str
    hints: list[DemoHintOut]
