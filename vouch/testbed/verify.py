#!/usr/bin/env python3
"""
Prove the testbed works before spending a single Bright Data credit.

For every variant: render the page, parse it back out the way a collector would, and run the REAL
guardian over it against the clean page's baseline. If a variant does not trip the check it was
designed to trip, the page is wrong and no amount of live scraping will fix it - better to learn
that here, offline, for free.

    python verify.py            # check every variant
    python verify.py --verbose  # also print each verdict's brief

This deliberately parses the rendered HTML rather than reusing the generator's dicts. Parsing is
what a scraper does, so a field that is unanchored in the markup - or a price a regex cannot pick
out of its element - shows up here as a failure rather than as a surprise on live infrastructure.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

from app.guardian.checks import FieldProfile, profile_run, run_all_checks  # noqa: E402
from app.guardian.verdict import decide                                    # noqa: E402

from generate import VARIANTS, apply_variant, base_rows, render            # noqa: E402

# The check each variant must trip, and nothing more.
#
# Only the CODE is asserted, not the decision. Whether a fired check crosses the hold threshold is
# the guardian's scoring POLICY (verdict.decide), and it is not this page's job to encode it - a
# testbed that asserted decisions would have to be edited every time the thresholds were tuned, and
# would start failing for a reason that has nothing to do with the page. The decision is printed,
# and any break that still lands on PASS is called out as a policy observation below.
EXPECTED: dict[str, str | None] = {
    "clean":    None,
    "swap":     "COLUMN_SWAP",
    "inverted": "VALUE_ORDER_INVERTED",
    "nulls":    "NULL_SPIKE",
    "missing":  "FIELD_MISSING",
    "collapse": "CARDINALITY_COLLAPSE",
    "instock":  "BOOL_RATIO_SHIFT",
    "drift":    "NUMERIC_DRIFT",
    "fake_sale": "REFERENCE_PRICE_UNSUPPORTED",
}

# Variants where a PASS verdict is the correct outcome, not a gap in the scoring policy. The heal is
# sound - we read the page exactly as written - and the finding is about what the SITE claims. Holding
# the repair for that would reject a good extraction for something it did not cause.
PASS_BY_DESIGN = {"fake_sale"}

_ITEM = re.compile(r'<li class="item">(.*?)</li>', re.S)
_TITLE = re.compile(r'<a class="item-title"[^>]*>(.*?)</a>', re.S)
_RATING = re.compile(r'<span class="rating">([\d.]+)</span>')
_CURRENT = re.compile(r'<span class="price-current">(.*?)</span>', re.S)
_WAS = re.compile(r'<span class="price-was">(.*?)</span>', re.S)
_SHIP = re.compile(r'<div class="price-ship">(.*?) Shipping</div>', re.S)
_STOCK = re.compile(r'<span class="stock (in|out)">')


def _num(text: str | None) -> float | None:
    """Pull a number out of a rendered money string, the way a scraper's numeric coercion would."""
    if not text:
        return None
    cleaned = text.replace("&mdash;", "").replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse(html: str) -> list[dict]:
    """Extract rows from the rendered page - one dict per tile, like a collector returns."""
    rows = []
    for block in _ITEM.findall(html):
        title = _TITLE.search(block)
        stock = _STOCK.search(block)
        row = {
            "name": title.group(1).strip() if title else None,
            "price": _num(_CURRENT.search(block).group(1) if _CURRENT.search(block) else None),
            "rating": _num(_RATING.search(block).group(1) if _RATING.search(block) else None),
            "in_stock": (stock.group(1) == "in") if stock else None,
        }
        was = _WAS.search(block)
        if was:
            row["original_price"] = _num(was.group(1))
        ship = _SHIP.search(block)
        if ship:
            row["shipping"] = _num(ship.group(1))
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    # The clean page is the baseline, exactly as the live flow would capture it.
    clean_rows = parse(render(apply_variant(base_rows(), "clean"), "clean"))
    if not clean_rows:
        print("FATAL: parsed 0 rows from the clean page - the markup and the parser disagree")
        return 1

    baseline = profile_run(clean_rows)
    baseline_count = len(clean_rows)

    print(f"baseline: {baseline_count} rows, fields {', '.join(sorted(baseline))}")
    for name in ("price", "shipping", "rating"):
        p = baseline.get(name)
        if p and p.dtype == "numeric":
            print(f"  {name:15} median ${p.median:>9,.2f}   range ${p.minimum:,.2f}-${p.maximum:,.2f}")
    print()

    failures = 0
    passes_anyway: list[tuple[str, str, int]] = []

    # What the clean page charged, per product. This IS the pre-sale record: in production it comes
    # from the confirmed CompetitorObservation rows, here from the page we captured the baseline off.
    # Passing it only to the sale variant mirrors reality - an ordinary heal has no sale to audit.
    before_sale = {r["name"]: r["price"] for r in clean_rows
                   if r.get("name") and r.get("price") is not None}

    for variant in VARIANTS:
        rows = apply_variant(base_rows(), variant)
        parsed = parse(render(rows, variant))
        refs = before_sale if variant == "fake_sale" else None
        verdict = decide(run_all_checks(baseline, parsed, baseline_count, reference_prices=refs))

        want_code = EXPECTED[variant]
        codes = {f.code for f in verdict.failures}
        primary = verdict.primary_failure

        ok = not codes if want_code is None else want_code in codes
        failures += 0 if ok else 1

        # A break that trips its check but still scores PASS is not a page bug - it is the scoring
        # policy declining to hold on this evidence. Worth surfacing rather than burying. fake_sale is
        # excluded because PASS is its DESIGNED outcome: the extraction is correct and the finding is
        # about the site's claim, so rejecting the heal would punish a good repair.
        if (want_code is not None and ok and verdict.decision == "pass"
                and variant not in PASS_BY_DESIGN):
            passes_anyway.append((variant, want_code, verdict.confidence))

        mark = "OK  " if ok else "FAIL"
        got = primary.code if primary else "-"
        print(f"[{mark}] {variant:9} {len(parsed):>3} rows  "
              f"{verdict.decision.upper():6} {verdict.confidence:>3}/100  "
              f"primary={got:22} want={want_code or '(none)'}")
        if args.verbose or not ok:
            print(f"         brief: {verdict.brief}")
            if codes:
                print(f"         all codes: {', '.join(sorted(codes))}")

    print()
    if passes_anyway:
        print("note - these breaks are DETECTED but still scored PASS, so nothing would be held:")
        for variant, code, conf in passes_anyway:
            print(f"    {variant:9} {code:22} {conf}/100 "
                  f"(a lone {'medium'} finding costs 10, and PASS needs only >=85)")
        print("  That is verdict.decide's policy, not a fault in this page. It does mean a page")
        print("  broken this way would ship a price change with a warning attached.")
        print()

    if failures:
        print(f"{failures} variant(s) did not trip their check - fix the page, not the checks")
        return 1
    print(f"all {len(VARIANTS)} variants trip the check they were designed to trip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
