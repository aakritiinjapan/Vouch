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

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, Column, JSON


def _now() -> datetime:
    return datetime.utcnow()


class ProposalStatus(str, Enum):
    PENDING = "pending"        # waiting for seller review
    APPROVED = "approved"      # seller (or auto-band) approved; price is live
    REJECTED = "rejected"      # seller declined
    HELD = "held"              # guardian couldn't confirm the source; do not act


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
    sku: str = Field(index=True)
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


class Baseline(SQLModel, table=True):
    """Last-known-good profile of a collector's output — the guardian's reference point."""
    id: Optional[int] = Field(default=None, primary_key=True)
    collector_id: str = Field(index=True)
    record_count: int = 0
    # per-field statistical fingerprint, produced by guardian.checks.profile_run()
    field_profiles: dict = Field(default_factory=dict, sa_column=Column(JSON))
    captured_at: datetime = Field(default_factory=_now)
