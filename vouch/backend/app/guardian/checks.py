"""
The guardian's validation battery.

Given a *baseline* profile (the last-known-good run) and the *proposed* rows a self-heal wants to
commit, decide whether the heal preserved the MEANING of the data — not just its shape.

Checks run cheapest-first, so the deterministic tiers gate whether the expensive LLM judge
(guardian/judge.py) ever runs:

    Tier 1  structural   — fields present, types intact, null-rates sane, row count sane
    Tier 2  distributional — value distributions haven't drifted (this is what catches a heal that
                             returns the right shape but the wrong field)
    Tier 2b column-swap  — the money check: did two fields silently trade places?
    Tier 3  semantic     — (see guardian/judge.py) does the content still match the field's meaning?

Each check returns a CheckResult. guardian/verdict.py rolls them into a score + a plain brief.

No third-party deps — pure stdlib statistics — so this module is trivially testable and fast.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# Below this many rows a median is an anecdote, not a distribution. Bright Data's heal gate returns a
# preview SAMPLE - we have measured exactly 1 row against a 96-row baseline - so any check that reasons
# about volume or spread has to stand down rather than report the sample size as a finding.
MIN_ROWS_FOR_DISTRIBUTION = 5


class Severity(str, Enum):
    CRITICAL = "critical"   # meaning almost certainly broken (e.g. column swap)
    HIGH = "high"           # strong signal of a bad heal
    MEDIUM = "medium"       # suspicious; worth a human glance
    LOW = "low"             # minor


@dataclass
class FieldProfile:
    name: str
    dtype: str                       # "numeric" | "string" | "bool" | "unknown"
    count: int
    null_rate: float
    # numeric
    median: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    # bool
    true_rate: Optional[float] = None
    # string
    mean_len: Optional[float] = None
    cardinality: Optional[int] = None
    sample: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "FieldProfile":
        return cls(**d)


@dataclass
class CheckResult:
    passed: bool
    severity: Severity
    field_name: str
    code: str                        # machine tag, e.g. "COLUMN_SWAP"
    message: str                     # plain-English, shown to the user
    evidence: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Profiling
# --------------------------------------------------------------------------------------

def _coerce_number(v: Any) -> Optional[float]:
    """Best-effort numeric parse: strips currency symbols, commas, whitespace."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    try:
        return float(s)
    except ValueError:
        return None


def _infer_dtype(values: list[Any]) -> str:
    non_null = [v for v in values if v not in (None, "")]
    if not non_null:
        return "unknown"
    if all(isinstance(v, bool) for v in non_null):
        return "bool"
    if sum(1 for v in non_null if _coerce_number(v) is not None) >= 0.8 * len(non_null):
        return "numeric"
    return "string"


def profile_field(name: str, values: list[Any]) -> FieldProfile:
    n = len(values)
    nulls = sum(1 for v in values if v in (None, ""))
    dtype = _infer_dtype(values)
    prof = FieldProfile(
        name=name, dtype=dtype, count=n,
        null_rate=(nulls / n if n else 1.0),
        sample=[v for v in values if v not in (None, "")][:5],
    )
    if dtype == "numeric":
        nums = sorted(x for x in (_coerce_number(v) for v in values) if x is not None)
        if nums:
            prof.median = statistics.median(nums)
            prof.minimum, prof.maximum = nums[0], nums[-1]
            if len(nums) >= 4:
                prof.q1 = nums[len(nums) // 4]
                prof.q3 = nums[(3 * len(nums)) // 4]
    elif dtype == "bool":
        bools = [v for v in values if isinstance(v, bool)]
        if bools:
            prof.true_rate = sum(1 for v in bools if v) / len(bools)
    elif dtype == "string":
        strs = [str(v) for v in values if v not in (None, "")]
        if strs:
            prof.mean_len = sum(len(s) for s in strs) / len(strs)
            prof.cardinality = len(set(strs))
    return prof


def profile_run(records: list[dict]) -> dict[str, FieldProfile]:
    """Turn a list of record dicts into a per-field profile. This is what we store as a Baseline."""
    if not records:
        return {}
    fields: dict[str, list[Any]] = {}
    for rec in records:
        for k, v in rec.items():
            fields.setdefault(k, []).append(v)
    # pad missing keys so counts line up
    n = len(records)
    for k in fields:
        while len(fields[k]) < n:
            fields[k].append(None)
    return {k: profile_field(k, vals) for k, vals in fields.items()}


# --------------------------------------------------------------------------------------
# Tier 1 — structural
# --------------------------------------------------------------------------------------

def check_field_presence(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile]) -> list[CheckResult]:
    out = []
    for name in baseline:
        if name not in proposed:
            out.append(CheckResult(
                False, Severity.CRITICAL, name, "FIELD_MISSING",
                f"Field '{name}' disappeared after the heal.",
                {"expected": name},
            ))
    return out


def check_null_rate(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile],
                    jump: float = 0.2) -> list[CheckResult]:
    out = []
    for name, base in baseline.items():
        prop = proposed.get(name)
        if prop and prop.null_rate - base.null_rate > jump:
            out.append(CheckResult(
                False, Severity.HIGH, name, "NULL_SPIKE",
                f"'{name}' is empty on {prop.null_rate:.0%} of rows (was {base.null_rate:.0%}).",
                {"baseline_null_rate": base.null_rate, "proposed_null_rate": prop.null_rate},
            ))
    return out


def check_record_count(baseline_count: int, proposed_count: int, tol: float = 0.5) -> list[CheckResult]:
    if baseline_count == 0:
        return []
    ratio = proposed_count / baseline_count
    if ratio < (1 - tol) or ratio > (1 + tol):
        return [CheckResult(
            False, Severity.MEDIUM, "__run__", "ROW_COUNT_SHIFT",
            f"Row count changed from {baseline_count} to {proposed_count}.",
            {"baseline": baseline_count, "proposed": proposed_count},
        )]
    return []


# --------------------------------------------------------------------------------------
# Tier 2 — distributional (catches right-shape-wrong-meaning)
# --------------------------------------------------------------------------------------

def _rel_shift(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return abs(a - b) / max(abs(a), 1.0)


def check_numeric_drift(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile],
                        max_median_shift: float = 0.5) -> list[CheckResult]:
    out = []
    for name, base in baseline.items():
        prop = proposed.get(name)
        if not prop or base.dtype != "numeric" or prop.dtype != "numeric":
            continue
        shift = _rel_shift(base.median, prop.median)
        if shift is not None and shift > max_median_shift:
            out.append(CheckResult(
                False, Severity.HIGH, name, "NUMERIC_DRIFT",
                f"'{name}' median moved from {base.median:g} to {prop.median:g} "
                f"({shift:.0%} shift) — the heal may be reading a different value.",
                {"baseline_median": base.median, "proposed_median": prop.median, "shift": shift},
            ))
    return out


def check_cardinality_collapse(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile]) -> list[CheckResult]:
    out = []
    for name, base in baseline.items():
        prop = proposed.get(name)
        if not prop or base.cardinality is None or prop.cardinality is None:
            continue
        if base.cardinality >= 10 and prop.cardinality <= max(3, base.cardinality * 0.1):
            out.append(CheckResult(
                False, Severity.MEDIUM, name, "CARDINALITY_COLLAPSE",
                f"'{name}' went from {base.cardinality} distinct values to {prop.cardinality} — "
                f"it may now be pinned to a static element.",
                {"baseline_cardinality": base.cardinality, "proposed_cardinality": prop.cardinality},
            ))
    return out


def _profile_distance(prop: FieldProfile, base: FieldProfile) -> Optional[float]:
    """Mean relative distance between two numeric profiles across median, min and max.

    Comparing medians alone is too weak to distinguish a real column swap from a field that merely
    drifted toward a neighbour's typical value. A genuine swap transposes the whole distribution,
    so min and max move onto the other field's too - and profile_field already computes them.

    On a small sample min == max == median, so those two terms carry no information and actively
    distort the result: a single mid-priced row scores far from its own baseline's min and max and can
    therefore look closer to some other field. Below MIN_ROWS_FOR_DISTRIBUTION we compare medians only.
    """
    spread_is_meaningful = (prop.count >= MIN_ROWS_FOR_DISTRIBUTION
                            and base.count >= MIN_ROWS_FOR_DISTRIBUTION)
    pairs = [(prop.median, base.median)]
    if spread_is_meaningful:
        pairs += [(prop.minimum, base.minimum), (prop.maximum, base.maximum)]

    comps = []
    for a, b in pairs:
        if a is None or b is None:
            continue
        comps.append(abs(a - b) / max(abs(b), 1.0))
    return sum(comps) / len(comps) if comps else None


def check_column_swap(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile],
                      ratio: float = 0.34, max_other_dist: float = 0.25,
                      min_separation: float = 0.5) -> list[CheckResult]:
    """
    The money check.

    For each numeric field, ask: does the proposed value distribution look MORE like some *other*
    baseline field than like its own baseline? If the proposed 'price' distribution sits right on top
    of the baseline 'shipping' distribution (and far from the baseline 'price' one), the heal has
    silently swapped the columns - the exact failure a normal repricer would never notice.

    Three conditions must ALL hold before we call it a swap, because a false CRITICAL here holds a
    price change for no reason:
      1. the other field explains the values far better than its own baseline does (`ratio`);
      2. the values genuinely sit ON that other field's distribution (`max_other_dist`) - "closer to
         the other one" is not the same as "is the other one";
      3. the two baseline fields were distinguishable to begin with (`min_separation`). If two
         baseline fields already look alike, "closer to the other" is noise, not evidence.
    """
    out = []
    base_numeric = {n: p for n, p in baseline.items() if p.dtype == "numeric" and p.median is not None}
    for name, prop in proposed.items():
        if prop.dtype != "numeric" or prop.median is None or name not in base_numeric:
            continue
        own_dist = _profile_distance(prop, base_numeric[name])
        if own_dist is None or own_dist <= 0:
            continue
        others = {n: _profile_distance(prop, p) for n, p in base_numeric.items() if n != name}
        others = {n: d for n, d in others.items() if d is not None}
        if not others:
            continue
        best_other, best_dist = min(others.items(), key=lambda kv: kv[1])

        if best_dist >= own_dist * ratio:
            continue                      # (1) its own baseline still explains it well enough
        if best_dist > max_other_dist:
            continue                      # (2) not actually sitting on the other distribution
        separation = _profile_distance(base_numeric[best_other], base_numeric[name])
        if separation is None or separation < min_separation:
            continue                      # (3) the two fields are not distinguishable at baseline

        out.append(CheckResult(
            False, Severity.CRITICAL, name, "COLUMN_SWAP",
            f"'{name}' now matches the baseline distribution of '{best_other}', not '{name}'. "
            f"The heal likely swapped these fields.",
            {"field": name, "looks_like": best_other,
             "proposed_median": prop.median,
             "baseline_own_median": base_numeric[name].median,
             "baseline_other_median": base_numeric[best_other].median,
             "own_distance": round(own_dist, 4),
             "other_distance": round(best_dist, 4)},
        ))
    return out


def check_bool_ratio(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile],
                     jump: float = 0.5) -> list[CheckResult]:
    """Boolean fields were entirely uncovered by the battery, so an 'in_stock' that silently pins
    to a constant was invisible. Compares the share of true values across the whole column."""
    out = []
    for name, base in baseline.items():
        prop = proposed.get(name)
        if not prop or base.dtype != "bool" or prop.dtype != "bool":
            continue
        if base.true_rate is None or prop.true_rate is None:
            continue
        base_rate, prop_rate = base.true_rate, prop.true_rate
        if abs(prop_rate - base_rate) > jump:
            out.append(CheckResult(
                False, Severity.MEDIUM, name, "BOOL_RATIO_SHIFT",
                f"'{name}' is now {prop_rate:.0%} true (was {base_rate:.0%}) - it may be pinned "
                f"to a static element.",
                {"baseline_true_rate": base_rate, "proposed_true_rate": prop_rate},
            ))
    return out


# --------------------------------------------------------------------------------------
# Tier 2c - value invariants (catches the swap that distributions CANNOT see)
# --------------------------------------------------------------------------------------

# Pairs of fields with a guaranteed ordering: (lower, upper). A sale price can never exceed the list
# price it is discounted from, a discounted price can never exceed the original.
#
# Why this check has to exist. check_column_swap compares DISTRIBUTIONS, so it only works when the two
# fields look different - price (~$1,275) against shipping (~$17) is unmistakable. But the swap this
# product was pitched on is sale price against crossed-out ORIGINAL price, and those differ by maybe
# 10-30%. That is far too little to move a median past check_numeric_drift's threshold, and
# check_column_swap deliberately refuses to compare fields whose baselines are that similar, because
# for indistinguishable fields "closer to the other one" is noise.
#
# So the distributional tier is structurally blind here, and the fix is not a looser threshold - it is
# a different kind of evidence. An ordering invariant is absolute: it needs no baseline, it fires on
# the very first run, and an inversion on most rows is about as close to proof of a swap as scraped
# data offers.
FIELD_ORDERINGS: list[tuple[str, str]] = [
    ("price", "original_price"),
    ("price", "list_price"),
    ("sale_price", "original_price"),
]


def check_value_ordering(records: list[dict],
                         orderings: Optional[list[tuple[str, str]]] = None,
                         tolerance: float = 0.2) -> list[CheckResult]:
    """Flag pairs of fields whose guaranteed ordering has inverted.

    `tolerance` is the share of rows allowed to invert before it counts. Not zero: real listings do
    carry the occasional price-above-list oddity, and a single bad row should not hold a whole
    catalogue. A majority inversion, though, is a swap.
    """
    out: list[CheckResult] = []
    for lower_name, upper_name in (orderings if orderings is not None else FIELD_ORDERINGS):
        pairs = []
        for rec in records:
            lower = _coerce_number(rec.get(lower_name))
            upper = _coerce_number(rec.get(upper_name))
            if lower is None or upper is None:
                continue
            pairs.append((lower, upper))
        if not pairs:
            continue

        inverted = [(lo, up) for lo, up in pairs if lo > up]
        rate = len(inverted) / len(pairs)
        if rate <= tolerance:
            continue

        example = inverted[0]
        out.append(CheckResult(
            False, Severity.CRITICAL, lower_name, "VALUE_ORDER_INVERTED",
            f"'{lower_name}' is above '{upper_name}' on {rate:.0%} of rows "
            f"(e.g. {example[0]:g} vs {example[1]:g}). A sale price cannot exceed the price it is "
            f"discounted from - these two fields have almost certainly been swapped.",
            {"lower": lower_name, "upper": upper_name, "inverted_rate": rate,
             "rows_checked": len(pairs), "example_lower": example[0], "example_upper": example[1]},
        ))
    return out


# --------------------------------------------------------------------------------------
# Tier 2d - claims about the past (the only check that is not about our own extraction)
# --------------------------------------------------------------------------------------

# Every other check in this module asks: did OUR scrape stop meaning what it meant? This one asks
# something different - is the SITE'S claim about its own past supported by what we recorded?
#
# It exists because of when scrapers break. A retailer relayouts its product pages for a sale, the
# extraction breaks on the new markup, and a heal repairs it. That is the ordinary loop. But the sale
# page also introduces a NEW claim - "was $1,271.99" - and the only party who can check it is one who
# was already watching before the sale began. A crossed-out number is unfalsifiable at the moment you
# read it; it is only checkable against a dated record.
#
# So this needs no price history beyond one confirmed observation per product from before the sale,
# which is exactly what CompetitorObservation already stores. The caller supplies them; keeping the
# lookup out of here is what keeps this module free of the database.
#
# NOTE ON SEVERITY - deliberately LOW, and not because it is unimportant.
# If this fires, our extraction may be perfectly correct: we read the page right, and the page is
# making a claim its own history does not support. Charging it as HIGH or CRITICAL would reject a
# GOOD heal for something that is not a defect in the heal. LOW keeps the verdict at PASS (100 - 3)
# so the repair still commits, while the finding is still reported and can be surfaced on its own.
# The severity encodes "this is not an extraction fault", not "this does not matter".

def check_reference_price(records: list[dict], reference_prices: dict[str, float],
                          *, name_field: str = "name", claim_field: str = "original_price",
                          tolerance: float = 0.02) -> list[CheckResult]:
    """Compare each row's claimed was-price against the price we confirmed before the sale.

    `reference_prices` maps a product name to the last price we observed and the guardian confirmed
    BEFORE the current sale started. A claimed original above that is a discount measured from a
    number nobody was charged.

    `tolerance` (2%) absorbs rounding and small legitimate movement between our last observation and
    the sale starting. Anything inside it is not evidence of anything.

    Nothing fires when `reference_prices` is empty, which is the normal case: an ordinary heal
    validation has no sale to audit and no business inventing one.
    """
    if not reference_prices:
        return []

    lookup = {str(k).strip().casefold(): v for k, v in reference_prices.items()}

    checked = 0
    inflated: list[dict] = []
    for rec in records:
        name = rec.get(name_field)
        claimed = _coerce_number(rec.get(claim_field))
        if name is None or claimed is None:
            continue
        prior = lookup.get(str(name).strip().casefold())
        if prior is None:
            continue
        checked += 1

        # Only an INFLATED claim is a finding. A claimed original below what we recorded understates
        # the discount, which is a retailer's own business and harms nobody.
        if claimed <= prior * (1 + tolerance):
            continue
        inflated.append({"product": str(name), "claimed_original": claimed,
                         "confirmed_before_sale": prior,
                         "overstated_by": round(claimed - prior, 2),
                         "current_price": _coerce_number(rec.get("price"))})

    if not inflated:
        return []

    # ONE result for the whole run, not one per row. Severity is a fixed cost in verdict._score, so a
    # per-row finding would charge the same fault 30 times and saturate the score to a FAIL - which is
    # both wrong (a good extraction would be rejected) and misleading (one policy, not 30 faults).
    # check_value_ordering aggregates for the same reason; this follows it.
    worst = max(inflated, key=lambda d: d["overstated_by"])
    total = round(sum(d["overstated_by"] for d in inflated), 2)
    rate = len(inflated) / checked

    return [CheckResult(
        False, Severity.LOW, claim_field, "REFERENCE_PRICE_UNSUPPORTED",
        f"{len(inflated)} of {checked} products advertise a was-price higher than anything we "
        f"recorded before this sale. The largest: '{worst['product']}' claims "
        f"{_fmt_money(worst['claimed_original'])}, but the last price we confirmed for it was "
        f"{_fmt_money(worst['confirmed_before_sale'])} - a shopper would see a discount "
        f"{_fmt_money(worst['overstated_by'])} deeper than our record supports.",
        {"products_affected": len(inflated), "products_checked": checked,
         "inflated_rate": rate, "total_overstated": total,
         "worst_product": worst["product"],
         "claimed_original": worst["claimed_original"],
         "confirmed_before_sale": worst["confirmed_before_sale"],
         "overstated_by": worst["overstated_by"],
         "current_price": worst["current_price"],
         "examples": inflated[:5]},
    )]


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def run_all_checks(baseline_profiles: dict[str, FieldProfile], proposed_records: list[dict],
                   baseline_count: int, *, is_sample: bool = False,
                   reference_prices: Optional[dict[str, float]] = None) -> list[CheckResult]:
    """Run the deterministic tiers (1 + 2).

    Returns one CheckResult per FAILURE. Checks do not emit a result when they pass, so a
    clean run yields the single synthetic OK below - callers must not count passing results.

    `reference_prices` maps product name -> the price confirmed before the current sale. Supply it
    only when auditing a sale claim; omitted, check_reference_price stands down entirely. It is the
    one check here that judges the SITE rather than our own extraction, which is why it is scored LOW
    and cannot by itself reject an otherwise good heal - see its own note.

    `is_sample` says the proposed rows are a PREVIEW of what the heal would return, not the whole run.
    Bright Data's approval gate works that way: `preview_result` gave us 1 row against a 96-row
    baseline. Volume-dependent checks then measure the preview size instead of the heal, so
    ROW_COUNT_SHIFT and CARDINALITY_COLLAPSE stand down entirely, and the distributional checks stand
    down when there are too few rows for a median to mean anything.

    What still works on a one-row preview, and why it is enough to gate on:
      FIELD_MISSING          - a dropped field is visible in a single row
      NULL_SPIKE             - so is an empty one
      COLUMN_SWAP            - asks which distribution the values sit ON, not how they are spread
      VALUE_ORDER_INVERTED   - a row-wise invariant; one row is a complete test of it
    """
    proposed_profiles = profile_run(proposed_records)
    enough_rows = len(proposed_records) >= MIN_ROWS_FOR_DISTRIBUTION

    results: list[CheckResult] = []
    results += check_field_presence(baseline_profiles, proposed_profiles)
    results += check_null_rate(baseline_profiles, proposed_profiles)
    if not is_sample:
        results += check_record_count(baseline_count, len(proposed_records))
        results += check_cardinality_collapse(baseline_profiles, proposed_profiles)
    if enough_rows:
        results += check_numeric_drift(baseline_profiles, proposed_profiles)
    results += check_column_swap(baseline_profiles, proposed_profiles)
    results += check_bool_ratio(baseline_profiles, proposed_profiles)
    results += check_value_ordering(proposed_records)
    results += check_reference_price(proposed_records, reference_prices or {})

    if not results:
        results.append(CheckResult(True, Severity.LOW, "__run__", "OK",
                                   "All structural and distributional checks passed.", {}))
    return results
