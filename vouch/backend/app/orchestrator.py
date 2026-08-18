"""
The loop. For each product:

    1. run its competitor collector
    2. if the run looks degraded, heal — but validate the heal with the guardian BEFORE committing
    3. only trusted competitor prices reach the pricing engine
    4. produce a RepriceProposal the seller reviews (or a HELD one if the source is unconfirmed)

This is intentionally readable over clever — it's the spine the demo narrates. Claude Code should
wire it to the DB (models.py) and expose its outputs through api/routes.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.guardian.checks import FieldProfile, profile_run, run_all_checks
from app.guardian.verdict import Verdict, decide
from app.pricing import engine
from app.scraper import brightdata


@dataclass
class CycleOutcome:
    product_sku: str
    competitor_price: Optional[float]
    source_confirmed: bool
    verdict: Optional[Verdict]        # present iff a heal happened this cycle
    proposal: Optional[dict]          # {current_price, proposed_price, reason, status, confidence}


def _looks_degraded(baseline_profiles: dict[str, FieldProfile], records: list[dict]) -> bool:
    """Cheap gate: did this run come back empty, or with a null-spike vs. baseline?"""
    if not records:
        return True
    results = run_all_checks(baseline_profiles, records, baseline_count=len(records) or 1)
    return any(r.code in {"NULL_SPIKE", "FIELD_MISSING"} and not r.passed for r in results)


def run_cycle_for_product(product, baseline, *, _simulate_heal: Optional[str] = None) -> CycleOutcome:
    """
    `product`  : a Product row (has collector_id, competitor_url, my_price, cost, floor_margin)
    `baseline` : a Baseline row (has field_profiles dict + record_count) — last-known-good
    `_simulate_heal` : demo hook (mock only): force 'healed_good' or 'healed_swapped'
    """
    baseline_profiles = {k: FieldProfile.from_dict(v) for k, v in baseline.field_profiles.items()}

    records = brightdata.run(product.collector_id, product.competitor_url)
    verdict: Optional[Verdict] = None
    source_confirmed = True

    # 2. degraded? heal, then judge the heal at the gate.
    if _simulate_heal or _looks_degraded(baseline_profiles, records):
        prompt = _heal_prompt(product)
        proposal = brightdata.propose_heal(product.collector_id, prompt, product.competitor_url,
                                           _simulate=_simulate_heal)
        results = run_all_checks(baseline_profiles, proposal.proposed_records,
                                 baseline_count=baseline.record_count)
        verdict = decide(results)

        if verdict.confirmed:                       # PASS -> commit, trust the new data
            brightdata.approve_heal(product.collector_id)
            records = proposal.proposed_records
        else:                                       # FAIL/REVIEW -> reject, source is unconfirmed
            brightdata.reject_heal(product.collector_id)
            source_confirmed = False
            # (stretch) re-prompt heal with verdict.brief as the sharper diagnosis

    # 3–4. price only off confirmed data
    competitor_price = _extract_competitor_price(product, records) if source_confirmed else None

    if not source_confirmed:
        proposal_dict = {
            "current_price": product.my_price,
            "proposed_price": product.my_price,     # unchanged — we won't act
            "reason": (verdict.brief if verdict else "Competitor source could not be confirmed."),
            "status": "held",
            "confidence": (verdict.confidence if verdict else 0),
        }
    else:
        new_price, reason = engine.propose_price(product, competitor_price)
        proposal_dict = {
            "current_price": product.my_price,
            "proposed_price": new_price,
            "reason": reason,
            "status": "pending",
            "confidence": (verdict.confidence if verdict else 100),
        }

    return CycleOutcome(
        product_sku=product.sku,
        competitor_price=competitor_price,
        source_confirmed=source_confirmed,
        verdict=verdict,
        proposal=proposal_dict,
    )


def _heal_prompt(product) -> str:
    return (f"The competitor page changed. Extract the current SALE price of the product "
            f"(not the crossed-out original, not shipping) matching SKU {product.sku}.")


def _extract_competitor_price(product, records: list[dict]) -> Optional[float]:
    """Match this product's row in the scraped set and pull its price. Simplify as needed for demo."""
    from app.guardian.checks import _coerce_number
    for rec in records:
        if str(rec.get("name", "")).strip().lower() == product.name.strip().lower():
            return _coerce_number(rec.get("price"))
    return None
