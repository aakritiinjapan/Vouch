"""
The loop. For each product:

    1. run its competitor collector
    2. if the run looks degraded, heal - but validate the heal with the guardian BEFORE committing
    3. if the guardian rejects, feed its own diagnosis back as a sharper heal prompt and retry
    4. only trusted competitor prices reach the pricing engine
    5. produce a reprice proposal the seller reviews (or a HELD one if the source is unconfirmed)

This module is deliberately PURE. It reads attributes off the rows it is handed and returns
dataclasses; it may import models for type annotations, but it never opens a Session and never
commits - app/service.py owns every write. That split is what lets the whole cycle, including the
retry loop, be exercised against unsaved Product/Baseline instances with no database at all.

It is also free of `settings.mock_mode` branching: the mock/real split lives entirely inside
scraper/brightdata.py, so this file reads the same whether you are demoing or in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

from app.guardian import judge
from app.guardian.checks import FieldProfile, run_all_checks
from app.guardian.verdict import REVIEW, Verdict, apply_judge, decide
from app.models import Baseline, Product
from app.pricing import engine
from app.scraper import brightdata

# Hard cap on heal attempts per cycle. Two is deliberate: the demo needs exactly one re-prompt, and
# every further attempt is a real Scraper Studio heal costing real credits against an AI-Flow
# concurrency cap of 3 concurrent jobs. Enforced in the while condition, not by a break in the body.
MAX_HEAL_ATTEMPTS = 2

# Which check codes mean "this run came back broken enough to be worth healing". A degraded run is
# about missing data, not about values we disagree with - a drifted price is a real price.
_DEGRADATION_CODES = {"NULL_SPIKE", "FIELD_MISSING", "ROW_COUNT_SHIFT"}

SimulateHint = Union[str, Sequence[str], None]


@dataclass
class HealAttempt:
    """One trip through the approval gate. A cycle records every attempt, not just the last, so the
    event log can show the guardian's diagnosis turning into the next prompt."""
    attempt: int                          # 1-based
    prompt: str                           # the prompt actually sent (attempt 2 is the sharpened one)
    verdict: Verdict
    proposed_records: list[dict]
    committed: bool                       # True iff approve_heal() was called for this attempt


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

    attempts: list[HealAttempt] = []
    source_confirmed = True
    verdict: Optional[Verdict] = None
    counterfactual: Optional[dict] = None

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
                _simulate=_simulate_for_attempt(simulate_heal, attempt),
            )
            verdict = _judge_if_ambiguous(
                decide(run_all_checks(baseline_profiles, proposal.proposed_records,
                                      baseline_count=baseline.record_count,
                                      is_sample=proposal.is_sample)),
                proposal.proposed_records,
            )
            committed = verdict.confirmed

            if committed:
                brightdata.approve_heal(product.collector_id)   # at most once per cycle
                records = proposal.proposed_records
                source_confirmed = True
            else:
                # Reject every failed attempt so the collector never sits at an open approval gate.
                # Bright Data leaves the scraper unchanged on reject, which is what makes a retry
                # with a clearer prompt safe.
                brightdata.reject_heal(product.collector_id)
                source_confirmed = False

            attempts.append(HealAttempt(attempt=attempt, prompt=prompt, verdict=verdict,
                                        proposed_records=proposal.proposed_records,
                                        committed=committed))

            if committed or attempt >= max_heal_attempts:
                break

            # The guardian's own machine-readable diagnosis writes the next heal prompt.
            prompt = _resharpen_prompt(product, verdict)

    # The counterfactual describes the LAST REJECTED attempt: the number we refused to act on.
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
    )


def _judge_if_ambiguous(verdict: Verdict, records: list[dict]) -> Verdict:
    """Escalate to the Tier 3 semantic judge only when the cheap tiers could not decide.

    A clean PASS needs no second opinion and a CRITICAL FAIL has already been decided, so REVIEW is
    the only verdict worth spending an API call on. Outside MOCK_MODE with a key configured this is at
    most one call per held cycle; mocked, it is a no-op.
    """
    if verdict.decision != REVIEW:
        return verdict
    return apply_judge(verdict, judge.judge_fields(records))


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
