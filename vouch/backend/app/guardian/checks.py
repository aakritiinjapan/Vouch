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


def check_column_swap(baseline: dict[str, FieldProfile], proposed: dict[str, FieldProfile]) -> list[CheckResult]:
    """
    The money check.

    For each numeric field, ask: does the proposed value distribution look MORE like some *other*
    baseline field than like its own baseline? If the proposed 'price' median sits right on top of
    the baseline 'shipping' median (and far from the baseline 'price' median), the heal has silently
    swapped the columns — the exact failure a normal repricer would never notice.
    """
    out = []
    base_numeric = {n: p for n, p in baseline.items() if p.dtype == "numeric" and p.median is not None}
    for name, prop in proposed.items():
        if prop.dtype != "numeric" or prop.median is None or name not in base_numeric:
            continue
        own_dist = abs(prop.median - base_numeric[name].median)
        # nearest *other* baseline field by median
        others = {n: abs(prop.median - p.median) for n, p in base_numeric.items() if n != name}
        if not others:
            continue
        best_other, best_dist = min(others.items(), key=lambda kv: kv[1])
        # flag if another field explains the value far better than its own baseline does
        if best_dist < own_dist * 0.34 and own_dist > 0:
            out.append(CheckResult(
                False, Severity.CRITICAL, name, "COLUMN_SWAP",
                f"'{name}' now matches the baseline distribution of '{best_other}', not '{name}'. "
                f"The heal likely swapped these fields.",
                {"field": name, "looks_like": best_other,
                 "proposed_median": prop.median,
                 "baseline_own_median": base_numeric[name].median,
                 "baseline_other_median": base_numeric[best_other].median},
            ))
    return out


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def run_all_checks(baseline_profiles: dict[str, FieldProfile], proposed_records: list[dict],
                   baseline_count: int) -> list[CheckResult]:
    """Run the deterministic tiers (1 + 2). Returns ALL results, passed and failed."""
    proposed_profiles = profile_run(proposed_records)

    results: list[CheckResult] = []
    results += check_field_presence(baseline_profiles, proposed_profiles)
    results += check_null_rate(baseline_profiles, proposed_profiles)
    results += check_record_count(baseline_count, len(proposed_records))
    results += check_numeric_drift(baseline_profiles, proposed_profiles)
    results += check_cardinality_collapse(baseline_profiles, proposed_profiles)
    results += check_column_swap(baseline_profiles, proposed_profiles)

    if not results:
        results.append(CheckResult(True, Severity.LOW, "__run__", "OK",
                                   "All structural and distributional checks passed.", {}))
    return results
