"""
The persistence contract.

service.run_cycle writes a precise set of rows in each of three cases, and getting that wrong is
invisible until it is on a projector. These tests are that contract, executable.

The trust ratchet gets its own test: a REJECTED heal must never advance the baseline, or the guardian
slowly adopts the bad data as its own yardstick and stops being able to detect anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import service
from app.models import (
    Baseline,
    CompetitorObservation,
    HealEvent,
    HealStatus,
    HealVerdict,
    Product,
    ProposalStatus,
    RepriceProposal,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample_runs.json"
COLLECTOR = "c_mock_newegg_gpu"


def _fixture(key: str) -> list[dict]:
    return json.loads(FIXTURES.read_text())[key]


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def product(session) -> Product:
    p = Product(sku="GPU-5080-MSI", name="MSI RTX 5080 Gaming Trio",
                my_price=1319.00, cost=1050.00, floor_margin=0.08,
                competitor_url="https://example.com/newegg-mirror/rtx-5080-msi",
                collector_id=COLLECTOR)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _counts(session) -> dict:
    return {
        "heal_events": len(list(session.exec(select(HealEvent)))),
        "observations": len(list(session.exec(select(CompetitorObservation)))),
        "proposals": len(list(session.exec(select(RepriceProposal)))),
        "baselines": len(list(session.exec(select(Baseline)))),
    }


def _price_floor_in_baseline(session) -> float:
    baseline = session.exec(select(Baseline)).first()
    return baseline.field_profiles["price"]["minimum"]


# --------------------------------------------------------------------------------------
# Case A - a healthy run needs no heal
# --------------------------------------------------------------------------------------

def test_case_a_healthy_run(session, product):
    record = service.run_cycle(session, product)

    assert _counts(session) == {"heal_events": 0, "observations": 1, "proposals": 1, "baselines": 1}
    observation = session.exec(select(CompetitorObservation)).one()
    assert observation.confirmed is True
    assert observation.observed_price == 1299.99
    assert observation.run_id == record.cycle_id

    proposal = session.exec(select(RepriceProposal)).one()
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.confidence == 100
    assert proposal.heal_event_id is None
    assert proposal.counterfactual is None
    assert not record.baseline_refreshed, "an ordinary run must not advance the yardstick"


def test_a_no_op_reprice_is_not_written_at_all(session, product):
    """The queue is exception-based: a change of less than a cent is not a decision to review."""
    product.my_price = 1299.98        # already exactly a cent under the competitor
    session.add(product)
    session.commit()

    service.run_cycle(session, product)
    assert _counts(session)["proposals"] == 0
    assert _counts(session)["observations"] == 1, "we still record what we saw"


# --------------------------------------------------------------------------------------
# Case B - a heal that preserved meaning
# --------------------------------------------------------------------------------------

def test_case_b_heal_passes(session, product):
    before = None
    service.ensure_baseline(session, product)
    session.commit()
    before = _price_floor_in_baseline(session)

    record = service.run_cycle(session, product, simulate_run="run_degraded")

    assert _counts(session) == {"heal_events": 1, "observations": 1, "proposals": 1, "baselines": 1}
    event = session.exec(select(HealEvent)).one()
    assert event.status == HealStatus.APPROVED
    assert event.verdict == HealVerdict.PASS
    assert event.attempt == 1
    assert event.cycle_id == record.cycle_id
    assert "empty on 75% of rows" in event.trigger_reason, "a measured trigger, not a typed one"
    assert event.primary_check_code is None, "a passing heal has no failure to name"

    assert record.baseline_refreshed, "confirmed data may advance the baseline"
    assert _price_floor_in_baseline(session) != before

    proposal = session.exec(select(RepriceProposal)).one()
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.heal_event_id == event.id


# --------------------------------------------------------------------------------------
# Case C - a heal that changed meaning
# --------------------------------------------------------------------------------------

@pytest.fixture
def held(session, product):
    service.ensure_baseline(session, product)
    session.commit()
    floor_before = _price_floor_in_baseline(session)
    record = service.run_cycle(session, product,
                               simulate_heal=["healed_swapped", "healed_swapped"])
    return record, floor_before


def test_case_c_writes_one_event_per_attempt(session, held):
    record, _ = held
    assert _counts(session) == {"heal_events": 2, "observations": 1, "proposals": 1, "baselines": 1}

    events = list(session.exec(select(HealEvent).order_by(HealEvent.attempt)))
    assert [e.attempt for e in events] == [1, 2]
    assert all(e.status == HealStatus.REJECTED for e in events)
    assert all(e.verdict == HealVerdict.FAIL for e in events)
    assert all(e.primary_check_code == "COLUMN_SWAP" for e in events)
    assert events[0].evidence["looks_like"] == "shipping"
    assert events[1].prompt != events[0].prompt, "attempt 2 carries the sharpened prompt"
    assert all(e.cycle_id == record.cycle_id for e in events)


def test_case_c_does_not_advance_the_baseline(session, held):
    """The trust ratchet. Without this, a rejected heal poisons the reference it was judged against."""
    record, floor_before = held
    assert not record.baseline_refreshed
    assert _price_floor_in_baseline(session) == floor_before


def test_case_c_records_an_unconfirmed_observation(session, held):
    observation = session.exec(select(CompetitorObservation)).one()
    assert observation.confirmed is False
    assert observation.observed_price == 19.99, "the number we refused to act on"


def test_case_c_holds_the_reprice_with_a_counterfactual(session, held):
    proposal = session.exec(select(RepriceProposal)).one()
    assert proposal.status == ProposalStatus.HELD
    assert proposal.confidence == 40
    assert proposal.proposed_price == proposal.current_price, "a hold never moves the price"
    assert "Rejected this heal" in proposal.reason

    events = list(session.exec(select(HealEvent).order_by(HealEvent.attempt)))
    assert proposal.heal_event_id == events[-1].id, "explicit FK, not 'the latest for this product'"

    assert proposal.counterfactual["applied_price"] == 1134.00
    assert proposal.counterfactual["naive_price"] == 19.98


# --------------------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------------------

def test_a_held_proposal_cannot_be_approved_by_accident(session, held):
    proposal = session.exec(select(RepriceProposal)).one()
    with pytest.raises(service.Conflict) as exc:
        service.approve_proposal(session, proposal.id)
    assert exc.value.detail["check_code"] == "COLUMN_SWAP"
    assert exc.value.detail["confidence"] == 40

    session.refresh(proposal)
    assert proposal.status == ProposalStatus.HELD, "the refused approval must not have applied"


def test_overriding_a_hold_applies_the_floor_clamped_price(session, product, held):
    proposal = session.exec(select(RepriceProposal)).one()
    service.approve_proposal(session, proposal.id, force=True)

    session.refresh(product)
    assert product.my_price == 1134.00, "the engine's clamp, never the competitor's 19.99"
    session.refresh(proposal)
    assert proposal.status == ProposalStatus.APPROVED
    assert proposal.decided_at is not None


def test_approving_twice_is_a_conflict_not_a_double_apply(session, product):
    service.run_cycle(session, product)
    proposal = session.exec(select(RepriceProposal)).one()

    service.approve_proposal(session, proposal.id)
    session.refresh(product)
    applied_once = product.my_price

    with pytest.raises(service.Conflict):
        service.approve_proposal(session, proposal.id)
    session.refresh(product)
    assert product.my_price == applied_once


def test_approve_applies_the_price_and_stamps_the_product(session, product):
    service.run_cycle(session, product)
    proposal = session.exec(select(RepriceProposal)).one()
    service.approve_proposal(session, proposal.id)

    session.refresh(product)
    assert product.my_price == 1299.98      # a cent under the competitor's 1299.99


def test_reject_leaves_the_price_alone_and_keeps_the_note(session, product):
    service.run_cycle(session, product)
    proposal = session.exec(select(RepriceProposal)).one()
    before = product.my_price

    service.reject_proposal(session, proposal.id, note="skipped")
    session.refresh(product)
    session.refresh(proposal)
    assert product.my_price == before
    assert proposal.status == ProposalStatus.REJECTED
    assert "[skipped]" in proposal.reason


def test_approve_all_safe_skips_held_rows_and_explains_why(session, product, held):
    result = service.approve_all_safe(session)

    # the only proposal is HELD, so it is structurally out of scope for the bulk button
    assert result.approved == []
    proposal = session.exec(select(RepriceProposal)).one()
    assert proposal.status == ProposalStatus.HELD


def test_approve_all_safe_applies_a_routine_change(session, product):
    service.run_cycle(session, product)
    result = service.approve_all_safe(session)

    assert result.applied_count == 1
    assert result.skipped == []
    session.refresh(product)
    assert product.my_price == 1299.98


def test_approve_all_safe_skips_a_low_confidence_row_with_a_reason(session, product):
    service.run_cycle(session, product)
    proposal = session.exec(select(RepriceProposal)).one()
    proposal.confidence = 50
    session.add(proposal)
    session.commit()

    result = service.approve_all_safe(session)
    assert result.approved == []
    assert result.skipped[0]["id"] == proposal.id
    assert "confidence 50" in result.skipped[0]["why"]


# --------------------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------------------

def test_last_confirmed_observation_ignores_the_rejected_one(session, product, held):
    """The bug this prevents: after the resume beat, a query missing `confirmed == True` shows the
    price of a heal we rejected as the current competitor price."""
    assert service.last_confirmed_observation(session, product.id) is None, \
        "the only observation so far is unconfirmed"

    service.run_cycle(session, product)          # a clean cycle follows
    latest = service.last_confirmed_observation(session, product.id)
    assert latest is not None
    assert latest.observed_price == 1299.99
    assert latest.confirmed is True


def test_staleness_label_reads_like_a_product():
    from datetime import timedelta

    from app.models import _now

    assert service.staleness_label(None) == "never confirmed"
    assert service.staleness_label(_now()) == "last confirmed just now"
    assert service.staleness_label(_now() - timedelta(minutes=20)) == "last confirmed 20m ago"
    assert service.staleness_label(_now() - timedelta(hours=2)) == "last confirmed 2h ago"
    assert service.staleness_label(_now() - timedelta(days=3)) == "last confirmed 3d ago"


def test_heal_log_uses_scraper_studio_vocabulary(session, held):
    events = list(session.exec(select(HealEvent).order_by(HealEvent.attempt)))
    first = " | ".join(e["text"] for e in service.heal_log_entries(events[0]))
    second = " | ".join(e["text"] for e in service.heal_log_entries(events[1]))

    assert "awaiting approval" in first
    assert "COLUMN_SWAP" in first
    assert "confidence 40/100" in first
    assert "previous collector retained" in first
    assert "re-prompted with the guardian's diagnosis (attempt 2)" in second


# --------------------------------------------------------------------------------------
# what a heal event records about the verification, as distinct from about the finding
# --------------------------------------------------------------------------------------

def test_a_heal_event_records_how_much_was_looked_at(session, product):
    """Without this the study's two answers write the identical row.

    "PASS on two preview rows" and "PASS on thirty" are the same `verdict` and the same empty
    evidence dict; the difference lives entirely in the provenance, which is what these keys are.
    """
    service.run_cycle(session, product, simulate_run="run_degraded")
    event = session.exec(select(HealEvent)).one()

    assert event.evidence["full_battery"] is True
    assert event.evidence["verified_on"] == \
        "the approval gate returned the whole page — nothing further to run (8 of 8 rows)", \
        "MOCK_MODE's fixture is a full-size stand-in, so the gate IS the whole page"
    assert "checks_stood_down" not in event.evidence, "nothing stood down on a full run"


def test_everything_in_that_record_survives_the_card_that_renders_it(session, held):
    """The held card renders this dict generically: numbers go through a currency formatter and
    objects through String(). A row reading "$30.00" or "[object Object]" is a bug you only find on
    a projector, so the constraint is asserted here rather than remembered."""
    events = list(session.exec(select(HealEvent)))
    for event in events:
        for key in service.VERIFICATION_KEYS:
            if key in event.evidence:
                assert isinstance(event.evidence[key], (str, bool)), key


def test_a_rejected_heal_records_the_finding_and_the_provenance_side_by_side(session, held):
    events = list(session.exec(select(HealEvent).order_by(HealEvent.attempt)))
    evidence = events[0].evidence

    assert evidence["looks_like"] == "shipping", "the finding's own evidence"
    assert "8 of 8 rows" in evidence["verified_on"], "and how much of the page said so"


def test_the_operator_log_names_the_step_that_verified_the_heal(session, product):
    service.run_cycle(session, product, simulate_run="run_degraded")
    event = session.exec(select(HealEvent)).one()
    text = " | ".join(e["text"] for e in service.heal_log_entries(event))

    assert "verdict taken over the approval gate returned the whole page" in text
    assert "saved to production" in text, "the log says where the fix went, not just that it went"


def test_the_log_reads_the_real_gate_the_way_the_loop_walks_it(session):
    """The path MOCK_MODE cannot produce: a preview, then a full run, then the draft probe.

    Written against a HealEvent rather than a cycle because the subject is the vocabulary, and the
    loop that produces these facts has its own tests in test_orchestrator.py.
    """
    event = HealEvent(
        collector_id=COLLECTOR, trigger_reason="'price' is empty on 75% of rows",
        prompt="fix the price", proposed_confidence=95, verdict=HealVerdict.PASS,
        risk_brief="Heal verified.", status=HealStatus.APPROVED, attempt=1,
        evidence={
            "source_change": "'price' now reads '.price-ship', the element 'shipping' read before",
            "gate_decision": "review on 2 preview row(s) — a preview can reject, but it can never "
                             "confirm",
            "verified_on": "a full run of the healed template, not the gate's preview "
                           "(30 of 30 rows)",
            "draft_check": "production re-read after accepting: unchanged — the heal was still "
                           "only a draft",
        },
    )
    entries = service.heal_log_entries(event)
    text = " | ".join(e["text"] for e in entries)

    assert "source diff: 'price' now reads '.price-ship'" in text
    assert "a preview can reject, but it can never confirm" in text
    assert "verdict taken over a full run of the healed template" in text
    assert "(30 of 30 rows)" in text
    assert "production re-read after accepting: unchanged" in text
    assert [e["kind"] for e in entries] == [
        "run",       # what triggered it
        "heal",      # heal proposed - awaiting approval
        "heal",      # what the healer changed in the collector's source
        "verdict",   # the pre-filter on the preview, which could only ever have rejected
        "run",       # the full page the decision was taken over
        "run",       # production, read back
        "verdict",   # the one that decided
        "commit",
    ]


def test_the_log_never_invents_a_kind_the_frontend_cannot_render(session, held):
    """LogKind is a closed union in frontend/src/types.ts and the receipt draws a glyph per kind, so
    a sixth value ships as a blank circle. New steps reuse the five."""
    events = list(session.exec(select(HealEvent)))
    kinds = {e["kind"] for ev in events for e in service.heal_log_entries(ev)}
    assert kinds <= {"run", "heal", "verdict", "commit", "reprompt"}


def test_a_heal_event_from_before_this_existed_still_renders(session):
    """An empty evidence dict means we do not know how hard anyone looked. Say nothing, rather than
    print a reassuring line about a verification that may never have happened."""
    event = HealEvent(collector_id=COLLECTOR, trigger_reason="", prompt="p",
                      verdict=HealVerdict.FAIL, risk_brief="Rejected this heal.",
                      status=HealStatus.REJECTED, attempt=1, evidence={})
    text = " | ".join(e["text"] for e in service.heal_log_entries(event))

    assert "verified" not in text
    assert "previous collector retained" in text


def test_ensure_baseline_refuses_a_product_with_no_collector(session):
    orphan = Product(sku="X", name="X", my_price=1.0, cost=0.5,
                     competitor_url="https://example.com/x")
    session.add(orphan)
    session.commit()
    with pytest.raises(service.Unprocessable):
        service.ensure_baseline(session, orphan)


def test_run_all_cycles_rejects_an_unknown_sku(session, product):
    with pytest.raises(service.NotFound):
        service.run_all_cycles(session, skus=["NOPE"])


# --------------------------------------------------------------------------------------
# the resume beat, as two separate cycles
# --------------------------------------------------------------------------------------

def test_a_confirmed_cycle_supersedes_an_earlier_hold(session, product):
    """The demo runs the break and the resume as two separate cycles, so the hold written by the
    first must be closed by the second. Without this the held card never clears and the guardian
    looks like it can never change its mind."""
    service.run_cycle(session, product, simulate_heal=["healed_swapped", "healed_swapped"])
    held = session.exec(select(RepriceProposal)
                        .where(RepriceProposal.status == ProposalStatus.HELD)).all()
    assert len(held) == 1

    record = service.run_cycle(session, product, simulate_run="run_degraded",
                               simulate_heal="healed_swapped")

    assert record.superseded_proposal_ids == [held[0].id]
    session.refresh(held[0])
    assert held[0].status == ProposalStatus.SUPERSEDED, \
        "not REJECTED - the seller never declined it, the question stopped being open"
    assert held[0].decided_at is not None
    assert "superseded" in held[0].reason
    assert session.exec(select(RepriceProposal)
                        .where(RepriceProposal.status == ProposalStatus.HELD)).all() == []


def test_a_still_unconfirmed_cycle_leaves_the_hold_open(session, product):
    """Only a CONFIRMED cycle retires a hold. A second failure must not quietly clear the first."""
    service.run_cycle(session, product, simulate_heal=["healed_swapped", "healed_swapped"])
    record = service.run_cycle(session, product,
                              simulate_heal=["healed_swapped", "healed_swapped"])

    assert record.superseded_proposal_ids == []
    still_held = session.exec(select(RepriceProposal)
                              .where(RepriceProposal.status == ProposalStatus.HELD)).all()
    assert len(still_held) == 2, "both cycles held; neither may silently retire the other"


def test_an_already_decided_hold_is_not_re_touched(session, product):
    """A hold the seller already overrode must keep its APPROVED status and its decided_at."""
    service.run_cycle(session, product, simulate_heal=["healed_swapped", "healed_swapped"])
    held = session.exec(select(RepriceProposal)
                        .where(RepriceProposal.status == ProposalStatus.HELD)).one()
    service.approve_proposal(session, held.id, force=True)
    decided_at = held.decided_at

    service.run_cycle(session, product, simulate_run="run_degraded", simulate_heal="healed_swapped")
    session.refresh(held)
    assert held.status == ProposalStatus.APPROVED
    assert held.decided_at == decided_at
