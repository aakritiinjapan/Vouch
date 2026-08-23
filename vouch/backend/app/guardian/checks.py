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

Each check returns a CheckResult. run_all_checks returns those alongside an Evidence record saying
how many rows they were computed over, because what the checks found is only half of a verdict - a
clean result from two non-random rows and a clean result from a whole page are different facts, and
conflating them was a measured defect (see Evidence below). guardian/verdict.py rolls the pair into a
score + a plain brief.

No third-party deps — pure stdlib statistics — so this module is trivially testable and fast.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# Below this many rows a median is an anecdote, not a distribution. Bright Data's heal gate returns a
# preview SAMPLE, so any check that reasons about volume or spread has to stand down rather than
# report the sample size as a finding.
#
# CORRECTION, measured 2026-08-23 (docs/research/FINDINGS.md). The old comment here said the gate
# returns "exactly 1 row against a 96-row baseline". That reading was wrong twice over: the payload is
# `[{"products": [tile1, tile2, "28 more items"]}]`, so it is TWO rows plus a sentinel string, and the
# "1 row" was the nested container being counted as a record. Two rows does not change the conclusion
# below - it sharpens it, because two rows is still far under this threshold and, crucially, they are
# the first two tiles rather than a random pair.
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
# Evidence provenance - how much was actually looked at
# --------------------------------------------------------------------------------------

# WHY THIS TYPE EXISTS.
#
# Until 2026-08-23 a verdict recorded WHAT the checks found and nothing about HOW MUCH they were
# shown. A verdict computed from two rows was indistinguishable from one computed from thirty, so
# `decide()` returned PASS 100/100 on almost no evidence and the brief read "Heal verified".
#
# That is not a hypothetical. Reconstructed from docs/research/collector_p3.json, a real heal that
# put the shipping cost in the `price` field was judged:
#
#     rows judged            price median   distance to baseline `shipping`   verdict
#     gate preview (2/30)    $22.49         0.500                             PASS 100/100, no findings
#     full page   (30/30)    $14.99         0.000                             FAIL 40/100, COLUMN_SWAP
#
# The check was not broken. The sample was: the gate shows the FIRST two tiles, which on this
# catalogue are the expensive cards carrying the highest delivery charges ($24.99/$19.99 against a
# $14.99 population median). That bias alone puts the previewed values 0.500 from baseline shipping -
# exactly double check_column_swap's 0.25 threshold - so the check that exists to catch this error
# cannot fire, and its silence was being scored as reassurance.
#
# The rule that follows, and the one this type implements:
#
#     A PREVIEW CAN REJECT, BUT IT CAN NEVER CONFIRM.
#
# The asymmetry is the whole point. Rejecting on partial evidence is cheap and safe - the price
# simply does not move, and a heal held for a full run costs one more page load. Confirming on
# partial evidence is the measured failure above: a wrong price, committed, with a 100/100 next to it.


@dataclass(frozen=True)
class Evidence:
    """How many rows a verdict actually rests on, and whether that is all of them.

    `rows_judged`      rows the checks were run over. None means the caller never said - see
                       `unstated()`, which is the only thing that should produce it.
    `population_rows`  how many rows the healed template would return over the whole page, when that
                       is known. Bright Data's gate states it as a sentinel string - the preview is
                       `[tile1, tile2, "28 more items"]`, so the population is 30. None means nobody
                       told us; that is unknown, NOT "the same as rows_judged".
    `declared_sample`  the caller said outright "these rows are a preview". Independent of the counts
                       because it is knowable when the population is not.

    Frozen because a verdict's provenance is a fact about a computation that already happened. Nothing
    downstream has any business editing how much was looked at.
    """

    rows_judged: Optional[int]
    population_rows: Optional[int] = None
    declared_sample: bool = False

    @classmethod
    def unstated(cls) -> "Evidence":
        """Provenance for results whose caller never described them.

        Deliberately not the same value as "a full run of one row". Nobody claimed a sample and no
        population contradicts what was judged, so this behaves as full evidence - that is the legacy
        contract and holding it forever would break the product - but the counts stay None so a brief
        or a UI can never quote a row number that was never measured.
        """
        return cls(rows_judged=None)

    @property
    def is_partial(self) -> bool:
        """True when the checks did NOT see the whole population.

        Three independent ways to be partial, and each has to be its own clause:

          - nothing was judged at all. Zero rows is the weakest evidence there is, and it must never
            read as a clean bill of health;
          - the caller declared a sample AND we cannot rule out that more rows exist. Note the second
            half: a gate preview whose sentinel says there are no further items IS the whole page, and
            calling that partial would hold a heal we have in fact seen in full;
          - the population is known and we judged less of it than that, whatever the caller declared.
            A truncated "full" run is partial evidence no matter what it was labelled.
        """
        if self.rows_judged is not None and self.rows_judged <= 0:
            return True
        if (self.population_rows is not None and self.rows_judged is not None
                and self.rows_judged < self.population_rows):
            return True
        return self.declared_sample and self.population_rows is None

    @property
    def is_full(self) -> bool:
        return not self.is_partial

    @property
    def coverage(self) -> Optional[float]:
        """Share of the population judged, or None when either number is unknown.

        Unknown is returned rather than guessed. A caller that wants to render a percentage must
        decide for itself what to show when there is no denominator; inventing 1.0 here would put a
        "100% of rows" label on a verdict that never counted them.
        """
        if self.population_rows is None or self.population_rows <= 0 or self.rows_judged is None:
            return None
        return min(1.0, self.rows_judged / self.population_rows)

    def describe(self) -> str:
        """The provenance in the words a brief uses. No check vocabulary, no percentages."""
        if self.rows_judged is None:
            return "an unrecorded number of rows"
        if self.rows_judged <= 0:
            return "no rows at all"
        if self.population_rows is not None:
            return f"{self.rows_judged} of {self.population_rows} rows"
        if self.declared_sample:
            return f"{self.rows_judged} preview rows of an unknown total"
        return f"{self.rows_judged} rows"

    def to_dict(self) -> dict:
        return {"rows_judged": self.rows_judged, "population_rows": self.population_rows,
                "declared_sample": self.declared_sample, "is_partial": self.is_partial,
                "coverage": self.coverage}


class CheckBattery(list):
    """The battery's results, which are a list of CheckResult PLUS the provenance of that list.

    Why a list subclass rather than a tuple or a new record type: every existing caller of
    `run_all_checks` treats the return value as a plain list - iterating it, `len`-ing it, passing it
    straight into `decide`. Widening the return type this way keeps all of them working unchanged
    while making the provenance travel WITH the findings instead of alongside them.

    That coupling is deliberate and it is the safety property. `decide` reads `.evidence` off the
    battery automatically, so the one call site that knows how many rows there were - `run_all_checks`,
    which was handed them - is the one that records it. A caller cannot forget to pass it on, and
    therefore cannot accidentally recreate the "PASS 100/100 on two rows" bug by omission.

    A hand-built plain list has no provenance, and `decide` treats that as full evidence. That is the
    legacy contract (`decide([...])` in tests and in callers that judged a complete run) and changing
    it would hold every verdict forever. It is the one door left open, so build results through
    `run_all_checks` unless you are prepared to state the evidence yourself.
    """

    def __init__(self, results, evidence: Evidence, stood_down: tuple[str, ...] = ()):
        # `evidence` is required, with no default. A default would have to be a guess about how much
        # was looked at, and every possible guess is wrong in a way that matters: "full" reinstates
        # the bug, "empty" holds verdicts that were earned. Whoever has the rows states the number.
        super().__init__(results)
        self.evidence = evidence
        # The codes that could not run at all, so were never in a position to fire. This is the
        # difference between "we looked and it was fine" and "we could not look", which an empty
        # failure list flattens into one indistinguishable answer. A consumer gating on this verdict
        # needs that distinction more than it needs any individual finding: a clean result with
        # COLUMN_SWAP stood down is not evidence of no swap.
        self.stood_down = tuple(stood_down)


# --------------------------------------------------------------------------------------
# Profiling
# --------------------------------------------------------------------------------------

def _coerce_number(v: Any) -> Optional[float]:
    """Best-effort numeric parse: strips currency symbols, commas, whitespace.

    Also unwraps the `{"value": 1999.99, "currency": "USD"}` shape. That is not a hypothetical
    convenience - it is what Bright Data's approval gate actually returns for money fields
    (docs/research/FINDINGS.md, defect 3). The scraper adapter flattens it before the battery sees
    it, but the row-wise checks are also reachable from the public /verify endpoint with caller-
    supplied records, and there `str({'value': 24.99})` parses to None: every comparison silently
    skips, and check_value_ordering - the one check that catches a sale/original swap - reports
    nothing at all on a whole catalogue. Silence that looks like a pass is precisely the failure
    mode this module is being hardened against, so the unwrap belongs at the bottom, not upstream.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        # bool is a subclass of int. True would coerce to 1.0 and let an in_stock column be compared
        # against a price, which is meaningless arithmetic dressed up as a measurement.
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return _coerce_number(v.get("value")) if "value" in v else None
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


# Which dtype transitions are worth reporting. Anything involving "unknown" is excluded on purpose:
# unknown means every value was null, which is check_null_rate's finding to report and would be
# double-charged here. numeric <-> bool is excluded too, because _infer_dtype's own rules make that
# transition mostly an artefact of how few values it had to look at.
_TYPE_FLIPS_WORTH_REPORTING = {
    ("numeric", "string"), ("bool", "string"), ("string", "numeric"), ("string", "bool"),
}


def check_type_flip(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile]) -> list[CheckResult]:
    """Flag a field whose values stopped being the KIND of thing they were.

    This closes a hole rather than tightening a threshold. Every comparison in Tier 2 requires both
    sides to share a dtype - check_numeric_drift skips unless both are numeric, check_column_swap
    only looks at numeric profiles, check_bool_ratio only at bools, check_cardinality_collapse only
    at strings. So a heal that turns `price` from 1299.99 into "Add to Cart" on every row passes the
    entire battery in silence: the field is present, it is not null, and no check that could judge it
    is willing to run. The strongest possible signal was falling straight through the gaps between
    the checks that each declined to handle it.

    It also belongs to the small group of checks that genuinely survive a two-row preview, because a
    type is a property of the values themselves and needs no distribution to read.

    HIGH rather than CRITICAL. A dtype flip is near-conclusive that something broke, but _infer_dtype
    is a heuristic with an 80% majority rule, so on a short sample a couple of "N/A" rows can tip a
    real numeric column to `string`. HIGH holds the heal for review, which is the correct response to
    near-conclusive; CRITICAL would assert a certainty the inference does not have.
    """
    out = []
    for name, base in baseline.items():
        prop = proposed.get(name)
        if not prop:
            continue                      # absent entirely - check_field_presence owns that
        if (base.dtype, prop.dtype) not in _TYPE_FLIPS_WORTH_REPORTING:
            continue
        if prop.null_rate >= 1.0:
            continue                      # nothing left to have a type - check_null_rate owns that
        example = next((repr(v) for v in prop.sample), "(no example)")
        out.append(CheckResult(
            False, Severity.HIGH, name, "TYPE_CHANGED",
            f"'{name}' used to hold {base.dtype} values and now holds {prop.dtype} ones "
            f"(e.g. {example}) - the heal is reading a different element.",
            {"baseline_dtype": base.dtype, "proposed_dtype": prop.dtype,
             "example": prop.sample[:3]},
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

    The row-count test alone was not enough, and the gap was a live false-positive path. `count` is
    the number of ROWS, not the number of numeric values in them, so a 30-row run whose `price` came
    back null on 29 rows passed the count test while min == max == the one surviving value. The
    spread terms then measured that single number against a real baseline range and inflated the
    distance from the field's OWN baseline - which is the exact input that makes some other field
    look like the better explanation and raises a CRITICAL swap claim on what is really a null spike.
    So we test the thing the docstring always claimed to be testing: whether there is any spread at
    all. A degenerate min == max range is one value however many rows produced it.
    """
    spread_is_meaningful = (
        prop.count >= MIN_ROWS_FOR_DISTRIBUTION and base.count >= MIN_ROWS_FOR_DISTRIBUTION
        and None not in (prop.minimum, prop.maximum, base.minimum, base.maximum)
        and prop.minimum != prop.maximum and base.minimum != base.maximum
    )
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

    Rows where either side is zero or negative are not compared. A zero list price is not a claim
    that the item was once free - it is an absent value that a collector encoded as a number instead
    of as null, and it is a common shape. Comparing against it manufactures an inversion on EVERY
    row (`price 100 > original 0`) and turns an ordinary catalogue with no crossed-out prices into a
    CRITICAL swap claim. An invariant that fires on missing data is not an invariant.
    """
    out: list[CheckResult] = []
    for lower_name, upper_name in (orderings if orderings is not None else FIELD_ORDERINGS):
        pairs = []
        for rec in records:
            lower = _coerce_number(rec.get(lower_name))
            upper = _coerce_number(rec.get(upper_name))
            if lower is None or upper is None:
                continue
            if lower <= 0 or upper <= 0:
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

    # Coerce and filter the priors up front rather than trusting the annotation. This check is
    # reachable from /verify with caller-supplied JSON, so a "reference price" can arrive as
    # "$1,149.99", as None, or as 0. Only a positive number is a confirmed observation: a zero prior
    # would make every claimed was-price "inflated" by its own full value and report a whole
    # catalogue as fraudulent on the strength of a missing record.
    lookup: dict[str, float] = {}
    for k, v in reference_prices.items():
        prior = _coerce_number(v)
        if prior is not None and prior > 0:
            lookup[str(k).strip().casefold()] = prior
    if not lookup:
        return []

    checked = 0
    inflated: list[dict] = []
    for rec in records:
        name = rec.get(name_field)
        claimed = _coerce_number(rec.get(claim_field))
        if name is None or claimed is None or claimed <= 0:
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
                   population_rows: Optional[int] = None,
                   reference_prices: Optional[dict[str, float]] = None) -> CheckBattery:
    """Run the deterministic tiers (1 + 2).

    Returns a CheckBattery: one CheckResult per FAILURE, plus the Evidence describing how much was
    looked at. Checks do not emit a result when they pass, so a clean run yields the single synthetic
    OK below - callers must not count passing results. The Evidence rides along because a clean
    result list means nothing without it (see the Evidence docstring for the measurement that proves
    this); `decide` reads it off the battery with no wiring required at the call site.

    `reference_prices` maps product name -> the price confirmed before the current sale. Supply it
    only when auditing a sale claim; omitted, check_reference_price stands down entirely. It is the
    one check here that judges the SITE rather than our own extraction, which is why it is scored LOW
    and cannot by itself reject an otherwise good heal - see its own note.

    `is_sample` says the proposed rows are a PREVIEW of what the heal would return, not the whole run.
    Bright Data's approval gate works that way: `preview_result` is the first two tiles plus a literal
    `"28 more items"` string. Volume-dependent checks would otherwise measure the preview size instead
    of the heal, so ROW_COUNT_SHIFT and CARDINALITY_COLLAPSE stand down, and NUMERIC_DRIFT stands down
    when there are too few rows for a median to mean anything.

    `population_rows` is how many rows the healed template would return over the whole page, parsed
    from that sentinel. Two things change when it is known. The verdict can state its own coverage
    honestly ("2 of 30" rather than "2"), and ROW_COUNT_SHIFT comes back ON for samples - because the
    thing that check wants to compare against the baseline is the size of the HEALED RUN, and the
    sentinel states it exactly. Standing that check down for previews was only ever a workaround for
    not knowing the number.

    WHICH CHECKS SURVIVE A TWO-ROW PREVIEW - re-derived from measurement, 2026-08-23.
    The previous version of this list was written from first principles and one line of it was
    simply false. It claimed COLUMN_SWAP works on a preview because it "asks which distribution the
    values sit ON, not how they are spread", and offered that as the reason a preview was safe to
    gate on. Measured on the real payload in docs/research/, shipping-in-the-price-field scored
    PASS 100/100 with zero findings on the gate's 2 rows and FAIL 40/100 with COLUMN_SWAP CRITICAL on
    all 30. The claim was not merely optimistic; it was the justification for the wrong behaviour.

      Row-local invariants - a complete test on any single row, so a preview judges them as well as
      a full run does:
        FIELD_MISSING          a dropped field is visible in one row
        NULL_SPIKE             so is an empty one
        TYPE_CHANGED           a value's kind is a property of the value
        VALUE_ORDER_INVERTED   price > original_price is decided within one row. This is the check
                               that caught the OTHER misleading heal in the study, from the gate.

      Distribution-comparing - structurally unreliable on a preview, because the preview is the first
      N tiles rather than a random N:
        NUMERIC_DRIFT          stood down below MIN_ROWS_FOR_DISTRIBUTION; a median of two is an
                               anecdote and the two are not drawn at random
        COLUMN_SWAP            LEFT RUNNING, and the reasoning matters. Its false NEGATIVES on a
                               sample are common - that is the measured failure above. Its true
                               positives are still true: the guard conditions require the values to
                               sit ON another baseline field's distribution, near-miss is not enough,
                               and the two fields must have been distinguishable to begin with. A
                               swap it does detect in two rows is real evidence, and standing it down
                               would trade a cheap early rejection for nothing. What is NOT allowed
                               is reading its silence as reassurance, and that is now impossible:
                               `decide` caps any partial-evidence verdict below PASS, so the absence
                               of a distributional finding on a sample cannot confirm anything.

    That last sentence is the load-bearing one. Every "stands down" above used to be a hole, because
    a check that stands down produces no finding and no finding used to mean PASS. With provenance on
    the verdict, standing down costs a confirmation rather than granting one.
    """
    proposed_profiles = profile_run(proposed_records)
    enough_rows = len(proposed_records) >= MIN_ROWS_FOR_DISTRIBUTION
    evidence = Evidence(rows_judged=len(proposed_records), population_rows=population_rows,
                        declared_sample=is_sample)

    results: list[CheckResult] = []
    # Every check that could not run, recorded as it is skipped rather than reconstructed afterwards
    # from the same conditions. Deriving this list a second time would let the two copies disagree,
    # and the copy the caller sees is the one that would be wrong.
    stood_down: list[str] = []

    results += check_field_presence(baseline_profiles, proposed_profiles)
    results += check_null_rate(baseline_profiles, proposed_profiles)
    results += check_type_flip(baseline_profiles, proposed_profiles)

    # Row count: judged against the population when we know it, otherwise against the rows in hand -
    # and skipped entirely when the rows in hand are a preview of an unknown total, since then the
    # only number available is the preview's own size, which says nothing about the heal.
    if population_rows is not None:
        results += check_record_count(baseline_count, population_rows)
    elif not is_sample:
        results += check_record_count(baseline_count, len(proposed_records))
    else:
        stood_down.append("ROW_COUNT_SHIFT")

    if not is_sample:
        # Cardinality has no population equivalent: knowing 30 rows exist tells us nothing about how
        # many distinct values they hold, so this one stays down for every preview.
        results += check_cardinality_collapse(baseline_profiles, proposed_profiles)
    else:
        stood_down.append("CARDINALITY_COLLAPSE")

    if enough_rows:
        results += check_numeric_drift(baseline_profiles, proposed_profiles)
    else:
        stood_down.append("NUMERIC_DRIFT")

    results += check_column_swap(baseline_profiles, proposed_profiles)
    results += check_bool_ratio(baseline_profiles, proposed_profiles)
    results += check_value_ordering(proposed_records)

    # Deliberately NOT recorded as stood down when reference_prices is empty. `stood_down` means
    # "this check could have applied and we were unable to run it", which is a warning about the
    # evidence. No pre-sale record means there is no sale claim in scope at all - not applicable, not
    # unexamined - and it is the caller's own omission, so reporting it back tells them nothing they
    # did not just do. Folding not-applicable in here would make `full_battery` false on essentially
    # every ordinary heal, and a flag that is always false is one callers learn to ignore, which
    # would cost us the sample warning that actually matters.
    results += check_reference_price(proposed_records, reference_prices or {})

    if not results:
        results.append(CheckResult(True, Severity.LOW, "__run__", "OK",
                                   "All structural and distributional checks passed.", {}))
    return CheckBattery(results, evidence, tuple(stood_down))
