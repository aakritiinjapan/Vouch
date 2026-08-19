"""
REST surface for the dashboard.

Every route is thin on purpose: marshal arguments, call one service function, serialise the result.
All business logic lives in service.py and orchestrator.py so it stays testable without HTTP, and so
there is never a second implementation of a rule hiding in a request handler.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel import Session, select

from app import service
from app.api import schemas
from app.config import settings
from app.db import session_dep
from app.models import (
    Baseline,
    CompetitorObservation,
    HealEvent,
    Product,
    ProposalStatus,
    RepriceProposal,
)
from app.scraper import baseline as baseline_capture
from app.scraper.brightdata import _FIXTURES

router = APIRouter()


def _fixture_keys() -> set[str]:
    """Valid simulate hints, read from the fixture itself so the two can never drift apart.

    A typo therefore fails at the door with a 422 listing the real keys, instead of surfacing as a
    KeyError behind a spinner mid-demo.
    """
    data = json.loads(Path(_FIXTURES).read_text(encoding="utf-8"))
    return {k for k in data if not k.startswith("_")}


def _fail(err: service.ServiceError):
    raise HTTPException(status_code=err.status_code,
                        detail={"detail": err.message, **err.detail})


# --------------------------------------------------------------------------------------
# products
# --------------------------------------------------------------------------------------

@router.get("/products", response_model=list[schemas.ProductOut])
def list_products(session: Session = Depends(session_dep)):
    products = session.exec(select(Product).order_by(Product.sku)).all()
    return [schemas.build_product(session, p) for p in products]


@router.get("/products/{product_id}/history", response_model=schemas.HistoryOut)
def product_history(product_id: int, session: Session = Depends(session_dep)):
    """The price chart. `competitor_price` is null on an unconfirmed cycle so the gap is in the data
    itself - README section 7's honest-staleness rule, enforced server-side rather than by asking the
    renderer to remember."""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, detail={"detail": f"product {product_id} not found"})

    observations = session.exec(
        select(CompetitorObservation)
        .where(CompetitorObservation.product_id == product_id)
        .order_by(CompetitorObservation.created_at)
    ).all()

    points = [
        schemas.HistoryPoint(
            ts=o.created_at,
            ts_label=service.staleness_label(o.created_at).replace("last confirmed ", ""),
            my_price=product.my_price,
            competitor_price=(o.observed_price if o.confirmed else None),
            confirmed=bool(o.confirmed),
        )
        for o in observations
    ]

    held = session.exec(
        select(RepriceProposal)
        .where(RepriceProposal.product_id == product_id)
        .where(RepriceProposal.status == ProposalStatus.HELD)
        .order_by(RepriceProposal.created_at.desc())
    ).first()
    latest = service.last_confirmed_observation(session, product_id)

    return schemas.HistoryOut(
        product=schemas.ProductRef(id=product.id, sku=product.sku, name=product.name),
        points=points,
        counterfactual=(held.counterfactual if held else None),
        last_confirmed_label=service.staleness_label(latest.created_at if latest else None),
    )


# --------------------------------------------------------------------------------------
# proposals - the decision queue
# --------------------------------------------------------------------------------------

@router.get("/proposals", response_model=list[schemas.ProposalOut])
def list_proposals(
    status: Optional[list[str]] = Query(default=None,
                                        description="pending|held|approved|rejected, repeatable"),
    limit: int = Query(default=100, le=500),
    session: Session = Depends(session_dep),
):
    wanted = status or ["pending", "held"]
    try:
        statuses = [ProposalStatus(s) for s in wanted]
    except ValueError:
        raise HTTPException(422, detail={"detail": f"unknown status in {wanted}"})

    proposals = session.exec(
        select(RepriceProposal)
        .where(RepriceProposal.status.in_(statuses))
        .order_by(RepriceProposal.created_at.desc())
        .limit(limit)
    ).all()
    return [schemas.build_proposal(session, p) for p in proposals]


@router.post("/proposals/approve-safe", response_model=schemas.BulkApproveResponse)
def approve_safe(body: schemas.BulkApproveRequest = Body(default=schemas.BulkApproveRequest()),
                 session: Session = Depends(session_dep)):
    """The "Approve all safe changes" button.

    Held proposals are structurally out of scope - is_safe() requires PENDING - and every skip comes
    back with a reason, which is what makes this a product rather than a bulk UPDATE.
    """
    try:
        result = service.approve_all_safe(session, min_confidence=body.min_confidence,
                                          max_delta_pct=body.max_delta_pct)
    except service.ServiceError as err:
        _fail(err)

    products = session.exec(select(Product).order_by(Product.sku)).all()
    return schemas.BulkApproveResponse(
        approved=result.approved,
        applied_count=result.applied_count,
        skipped=result.skipped,
        products=[schemas.build_product(session, p) for p in products],
    )


@router.post("/proposals/{proposal_id}/approve", response_model=schemas.ApproveResponse)
def approve(proposal_id: int, force: bool = Query(default=False),
            session: Session = Depends(session_dep)):
    """Approving a HELD proposal requires force=true and returns 409 without it.

    That refusal is the product, not a safety rail bolted on afterwards: the whole promise is that you
    cannot act on a number Vouch could not verify without saying so deliberately.
    """
    try:
        proposal = service.approve_proposal(session, proposal_id, force=force)
    except service.ServiceError as err:
        _fail(err)

    product = session.get(Product, proposal.product_id)
    return schemas.ApproveResponse(
        proposal=schemas.build_proposal(session, proposal),
        product=schemas.build_product(session, product),
        applied_price=product.my_price,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=schemas.ProposalOut)
def reject(proposal_id: int, note: Optional[str] = Query(default=None),
           session: Session = Depends(session_dep)):
    """Also backs the held card's [Skip this cycle] - pass note=skipped."""
    try:
        proposal = service.reject_proposal(session, proposal_id, note=note)
    except service.ServiceError as err:
        _fail(err)
    return schemas.build_proposal(session, proposal)


# --------------------------------------------------------------------------------------
# heal events - the operator log
# --------------------------------------------------------------------------------------

@router.get("/heal-events", response_model=list[schemas.HealEventOut])
def list_heal_events(limit: int = Query(default=50, le=200),
                     product_id: Optional[int] = None,
                     session: Session = Depends(session_dep)):
    query = select(HealEvent)
    if product_id is not None:
        query = query.where(HealEvent.product_id == product_id)
    events = session.exec(
        query.order_by(HealEvent.created_at.desc(), HealEvent.id.desc()).limit(limit)
    ).all()
    return [schemas.build_heal_event(session, e) for e in events]


# --------------------------------------------------------------------------------------
# cycles - the demo's remote control
# --------------------------------------------------------------------------------------

@router.post("/cycles/run", response_model=schemas.CycleRunResponse)
def run_cycles(body: schemas.CycleRunRequest = Body(default=schemas.CycleRunRequest()),
               session: Session = Depends(session_dep)):
    """Run every product's cycle (serially - Bright Data caps concurrent AI-Flow jobs at 3).

    The simulate hints are MOCK-ONLY and the refusal is visible: outside MOCK_MODE they are dropped,
    `simulate_applied` comes back null, and a warning says so. Silently honouring them against a live
    collector would compromise the one thing this project claims.
    """
    warnings: list[str] = []
    requested = {"run": body.simulate_run, "heal": body.simulate_heal}
    simulate_run, simulate_heal = body.simulate_run, body.simulate_heal

    if (simulate_run or simulate_heal) and not settings.mock_mode:
        warnings.append("simulate ignored: MOCK_MODE is off, so the guardian judged live data")
        simulate_run = simulate_heal = None
    else:
        known = _fixture_keys()
        for label, value in (("simulate_run", simulate_run), ("simulate_heal", simulate_heal)):
            values = value if isinstance(value, list) else ([value] if value else [])
            unknown = [v for v in values if v not in known]
            if unknown:
                raise HTTPException(422, detail={
                    "detail": f"unknown {label} fixture key(s): {', '.join(map(str, unknown))}",
                    "known": sorted(known),
                })

    try:
        records = service.run_all_cycles(
            session, skus=body.skus, simulate_run=simulate_run,
            simulate_heal=simulate_heal, max_heal_attempts=body.max_attempts,
        )
    except service.ServiceError as err:
        _fail(err)

    return schemas.CycleRunResponse(
        mock_mode=settings.mock_mode,
        simulate_requested=requested,
        simulate_applied=({"run": simulate_run, "heal": simulate_heal}
                          if (simulate_run or simulate_heal) else None),
        warnings=warnings,
        cycles=[schemas.build_cycle_summary(r) for r in records],
    )


# --------------------------------------------------------------------------------------
# demo reset
# --------------------------------------------------------------------------------------

@router.post("/demo/reset")
def demo_reset(session: Session = Depends(session_dep)):
    """Restore the demo's opening state.

    Not a convenience. No-op suppression means a queue that has run one cycle too many is an EMPTY
    queue, so without this, rehearsing twice requires stopping the server and deleting the database.
    Gated on MOCK_MODE because it is the only destructive endpoint in the app.
    """
    if not settings.mock_mode:
        raise HTTPException(404, detail={"detail": "demo reset is only available in MOCK_MODE"})

    from scripts.seed import DEMO_PRODUCTS

    deleted = {"proposals": 0, "heal_events": 0, "observations": 0}
    for model, key in ((RepriceProposal, "proposals"), (HealEvent, "heal_events"),
                       (CompetitorObservation, "observations")):
        rows = session.exec(select(model)).all()
        deleted[key] = len(rows)
        for row in rows:
            session.delete(row)
    session.commit()

    seed_prices = {p["sku"]: p["my_price"] for p in DEMO_PRODUCTS}
    for product in session.exec(select(Product)).all():
        if product.sku in seed_prices:
            product.my_price = seed_prices[product.sku]
            session.add(product)

    rows = json.loads(Path(_FIXTURES).read_text(encoding="utf-8"))["baseline"]
    profiles, count = baseline_capture.capture(rows)
    for baseline in session.exec(select(Baseline)).all():
        baseline.field_profiles = profiles
        baseline.record_count = count
        session.add(baseline)
    session.commit()

    # rebuild the confirmed price history the chart needs
    from scripts.seed import _seed_history
    products = session.exec(select(Product).order_by(Product.sku)).all()
    history = _seed_history(session, list(products), rows)

    return {"reset": True, "deleted": deleted, "history_observations": history,
            "products": len(products)}
