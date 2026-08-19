"""
Data model for Vouch.

Five tables carry the whole product:

- Product           : a SKU we reprice, its economics, and which collector watches its competitor.
- CompetitorObservation : one scraped competitor price at a point in time.
- RepriceProposal   : a suggested price change awaiting the seller's decision (or auto-approved).
- HealEvent         : a self-heal that happened on a collector, and the guardian's verdict on it.
- Baseline          : the last-known-good statistical profile of a collector's output (the thing
                      the guardian validates each heal against).

SQLite via SQLModel keeps setup at zero for the hackathon. The types are all standard so a swap to
Postgres later is trivial.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, Column, JSON


def _now() -> datetime:
    """Naive UTC.

    Deliberately naive rather than timezone-aware: SQLite does not persist tzinfo, so storing
    aware datetimes hands naive ones back on read and turns every later comparison into a
    TypeError waiting to happen. Everything stored here is UTC by convention; formatting for
    humans is the API layer's job, never the browser's.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProposalStatus(str, Enum):
    PENDING = "pending"        # waiting for seller review
    APPROVED = "approved"      # seller (or auto-band) approved; price is live
    REJECTED = "rejected"      # seller declined
    HELD = "held"              # guardian couldn't confirm the source; do not act
    SUPERSEDED = "superseded"  # a later cycle confirmed the source, so this hold is stale


class HealVerdict(str, Enum):
    PASS = "pass"              # heal preserved meaning; safe to commit
    REVIEW = "review"          # ambiguous; escalate / mark source unconfirmed
    FAIL = "fail"              # heal changed meaning (e.g. column swap); reject


class HealStatus(str, Enum):
    PROPOSED = "proposed"      # heal generated, sitting at the approval gate
    APPROVED = "approved"      # committed to the collector
    REJECTED = "rejected"      # discarded; old collector retained


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(index=True, unique=True)
    name: str
    my_price: float                      # current live price on our catalog
    cost: float                          # unit cost — used to enforce the floor margin
    floor_margin: float = 0.10           # never propose a price below cost * (1 + floor_margin)
    competitor_url: str                  # the page we scrape for the competing price
    collector_id: Optional[str] = None   # Bright Data Scraper Studio collector (c_*)
    updated_at: datetime = Field(default_factory=_now)


class CompetitorObservation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    observed_price: Optional[float] = None
    source_url: str
    run_id: Optional[str] = None
    confirmed: bool = True               # False when the guardian couldn't stand behind this read
    created_at: datetime = Field(default_factory=_now)


class RepriceProposal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    current_price: float
    proposed_price: float
    reason: str                          # plain-English: why this price, or why it's held
    status: ProposalStatus = ProposalStatus.PENDING
    confidence: int = 100                # 0–100, inherited from the source data's guardian verdict
    created_at: datetime = Field(default_factory=_now)
    decided_at: Optional[datetime] = None

    # Which heal produced the data behind this proposal. An explicit FK, not "the latest HealEvent
    # for this product": one cycle can emit several attempts, so an ordering heuristic would flip a
    # held card's check code from the attempt that failed to the attempt that passed.
    heal_event_id: Optional[int] = Field(default=None, foreign_key="healevent.id")

    # "What if we had auto-approved this?" - computed once at cycle time from the rejected heal, so
    # the UI performs no pricing arithmetic of its own. None means there is no counterfactual to
    # show, which is a different thing from a counterfactual whose value happened to be null.
    counterfactual: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class HealEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    collector_id: str = Field(index=True)
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    trigger_reason: str                  # e.g. "price null on 40% of rows"
    prompt: str                          # the heal prompt sent to Scraper Studio
    proposed_confidence: int = 0         # guardian confidence in the proposed heal (0–100)
    verdict: Optional[HealVerdict] = None
    risk_brief: str = ""                 # plain-English summary of what the guardian found
    status: HealStatus = HealStatus.PROPOSED
    created_at: datetime = Field(default_factory=_now)

    # The machine tag of the most severe finding, e.g. "COLUMN_SWAP". Stored rather than re-derived:
    # the proposed rows are not persisted, and parsing it back out of risk_brief would mean
    # string-matching our own prose.
    primary_check_code: Optional[str] = None

    # That finding's evidence dict ({"looks_like": "shipping", medians, ...}). This is what lets the
    # held card compose "the healed price ($19.99) matches this competitor's SHIPPING column" from
    # stored facts instead of hardcoding the sentence in the frontend.
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON))

    attempt: int = 1                     # 1-based; the re-prompt loop emits one row per attempt
    cycle_id: Optional[str] = None       # groups every row a single cycle wrote


class Baseline(SQLModel, table=True):
    """Last-known-good profile of a collector's output — the guardian's reference point."""
    id: Optional[int] = Field(default=None, primary_key=True)
    collector_id: str = Field(index=True)
    record_count: int = 0
    # per-field statistical fingerprint, produced by guardian.checks.profile_run()
    field_profiles: dict = Field(default_factory=dict, sa_column=Column(JSON))
    captured_at: datetime = Field(default_factory=_now)
