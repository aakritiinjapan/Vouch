#!/usr/bin/env python3
"""
Prove the testbed works before spending a single Bright Data credit.

For every variant: render the page, parse it back out the way a collector would, and run the REAL
guardian over it against the clean page's baseline. If a variant does not trip the check it was
designed to trip, the page is wrong and no amount of live scraping will fix it - better to learn
that here, offline, for free.

    python verify.py            # check every variant, then the three adversarial pages
    python verify.py --verbose  # also print each verdict's brief

This deliberately parses the rendered HTML rather than reusing the generator's dicts. Parsing is
what a scraper does, so a field that is unanchored in the markup - or a price a regex cannot pick
out of its element - shows up here as a failure rather than as a surprise on live infrastructure.

The second half checks the adversarial pages, and it is checking something different. The data
variants ask "does the guardian notice?". The adversarial pages ask nothing of the guardian: they
are claims about Bright Data's healer, and the only thing that can be settled offline is whether
the PAGE is shaped the way the claim says it is. That matters more than it sounds - a malformed or
unwinnable fixture is a far cheaper explanation for a failed heal than a bug in the healer, and it
is the explanation a sceptical reader will reach for first. So each page is made to prove, offline,
that the right answer was reachable and that a specific wrong answer was reachable too.
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

from generate import ADVERSARIAL, VARIANTS, apply_variant, base_rows, render, rows_for  # noqa: E402

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


# --------------------------------------------------------------------------------------
# The adversarial pages - two readings of the same page, and which one the values agree with
# --------------------------------------------------------------------------------------
#
# Each page below is read TWICE: once the way a lazy anchor would read it (position, order) and once
# the way the collector description asks for (label, magnitude, name). If both readings returned the
# same rows the page would not be a test of anything, so the pair is the assertion - and the fact
# that the semantic reading recovers the clean page EXACTLY is what makes the fixture fair.

_PRICE_BLOCK = re.compile(r'<div class="item-price">(.*?)</div>', re.S)
_SPAN_TEXT = re.compile(r"<span[^>]*>(.*?)</span>", re.S)
_SHIP_BARE = re.compile(r'<div class="price-ship">(.*?)</div>', re.S)
_MONEY_TEXT = re.compile(r"\$[\d,]+\.\d{2}")


def _money_in(text: str | None) -> float | None:
    """The number a collector's numeric coercion keeps, label and all.

    `_num` above refuses anything that is not purely a money string, which is correct for the data
    variants. P1 deliberately leaves the word "Shipping" glued to a value, and a real extractor
    strips the text rather than giving up - assuming otherwise would flatter the fixture by turning
    a wrong-selector failure into a convenient null.
    """
    m = _MONEY_TEXT.search(text or "")
    return _num(m.group(0)) if m else None


def _tile_common(block: str) -> dict:
    """The fields no adversarial page touches, so the guardian is comparing like with like."""
    title, stock, was, rating = (_TITLE.search(block), _STOCK.search(block),
                                 _WAS.search(block), _RATING.search(block))
    return {
        "name": title.group(1).strip() if title else None,
        "rating": _num(rating.group(1)) if rating else None,
        "in_stock": (stock.group(1) == "in") if stock else None,
        "original_price": _money_in(was.group(1)) if was else None,
    }


# --- P1 -------------------------------------------------------------------------------

def _p1_positional(html: str) -> list[dict]:
    """P1 read by position: the first money node under `.item-price`, plus the delivery line.

    This is what a selector fitted to tile 1 produces - and it is also, to the value, what the
    incumbent `.price-current` selector already returns. That coincidence is the finding: the
    "repair" a one-row preview would approve is the break it was supposed to fix.
    """
    rows = []
    for block in _ITEM.findall(html):
        pb = _PRICE_BLOCK.search(block)
        spans = _SPAN_TEXT.findall(pb.group(1)) if pb else []
        ship = _SHIP_BARE.search(block)
        rows.append({**_tile_common(block),
                     "price": _money_in(spans[0]) if spans else None,
                     "shipping": _money_in(ship.group(1)) if ship else None})
    return rows


def _p1_semantic(html: str) -> list[dict]:
    """P1 read by label: shipping is the money that says "Shipping", price is the one that does not.

    Exactly what the collector description asks for, and correct on all thirty tiles - including
    tile 1, where the positional reading also happens to be correct. Both anchors fit the preview
    row; only this one survives the other twenty-nine.
    """
    rows = []
    for block in _ITEM.findall(html):
        found = [m.group(1) for m in (_CURRENT.search(block), _SHIP_BARE.search(block)) if m]
        bare = [t for t in found if "Shipping" not in t]
        labelled = [t for t in found if "Shipping" in t]
        rows.append({**_tile_common(block),
                     "price": _money_in(bare[0]) if bare else None,
                     "shipping": _money_in(labelled[0]) if labelled else None})
    return rows


# --- P2 -------------------------------------------------------------------------------

_MONEY_SPAN = re.compile(r'(<span class="money">([^<]*)</span>)')
_MONEY_PAIR = re.compile(r'<span class="money">[^<]*</span>\s*<span class="money">[^<]*</span>')
_BARE_MONEY = re.compile(r"^\$[\d,]+\.\d{2}$")


def _p2_rows(html: str, by_magnitude: bool) -> list[dict]:
    """P2 read by order, or by size. There is nothing else on the page to read it by."""
    rows = []
    for block in _ITEM.findall(html):
        values = [_money_in(text) for _, text in _MONEY_SPAN.findall(block)]
        values = [v for v in values if v is not None]
        if len(values) != 2:
            rows.append({**_tile_common(block), "price": None, "shipping": None})
            continue
        price, shipping = ((max(values), min(values)) if by_magnitude
                           else (values[0], values[1]))
        rows.append({**_tile_common(block), "price": price, "shipping": shipping})
    return rows


# --- P3 -------------------------------------------------------------------------------
#
# The renamed parser spells the new hooks out here rather than importing generate.RENAME. Deriving
# them from the map would make this a test of the map against itself; writing them down means the
# assertion is "the page really does carry these names", which is the thing a heal will be judged
# against.

_R_ITEM = re.compile(r'<li class="prod-card">(.*?)</li>', re.S)
_R_TITLE = re.compile(r'<a class="prod-card__name"[^>]*>(.*?)</a>', re.S)
_R_RATING = re.compile(r'<span class="stars-value">([\d.]+)</span>')
_R_CURRENT = re.compile(r'<span class="cost-now">(.*?)</span>', re.S)
_R_WAS = re.compile(r'<span class="cost-before">(.*?)</span>', re.S)
_R_SHIP = re.compile(r'<div class="cost-delivery">(.*?) Shipping</div>', re.S)
_R_STOCK = re.compile(r'<span class="avail-badge (yes|no)">')


def _parse_renamed(html: str) -> list[dict]:
    """The same extraction as `parse`, spelled in the post-rename vocabulary."""
    rows = []
    for block in _R_ITEM.findall(html):
        title, stock, was, ship = (_R_TITLE.search(block), _R_STOCK.search(block),
                                   _R_WAS.search(block), _R_SHIP.search(block))
        row = {
            "name": title.group(1).strip() if title else None,
            "price": _num(_R_CURRENT.search(block).group(1) if _R_CURRENT.search(block) else None),
            "rating": _num(_R_RATING.search(block).group(1)) if _R_RATING.search(block) else None,
            "in_stock": (stock.group(1) == "yes") if stock else None,
        }
        if was:
            row["original_price"] = _num(was.group(1))
        if ship:
            row["shipping"] = _num(ship.group(1))
        rows.append(row)
    return rows


_CLASS_VALUE = re.compile(r'class="([^"]*)"')
_CSS_SELECTOR = re.compile(r"\.[A-Za-z][\w-]*")
_STYLE_BLOCK = re.compile(r"<style>(.*?)</style>", re.S)
_BANNER = re.compile(r"<!--.*?-->", re.S)
_FOOTER_VARIANT = re.compile(r"<code>[^<]*</code>")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")


def _hooks(html: str) -> set[str]:
    return {t for m in _CLASS_VALUE.findall(html) for t in m.split()}


def _blank_hooks(html: str) -> str:
    """Everything the page is EXCEPT its class names - markup, prose, values, stylesheet rules.

    Reduced by SHAPE, not by generate.RENAME: blank every class attribute value and every class
    selector, then the two documents must be byte-identical. Un-renaming with the map and comparing
    would only prove the map is its own inverse. This asks the independent question - is anything at
    all different other than a class name? - and the answer has to be no, or a failed P3 heal has an
    innocent explanation and the highest-severity hypothesis is unfalsifiable.

    The generator's provenance banner and footer stamp are excluded because they name the variant on
    purpose; they are the one place the two files are MEANT to differ.
    """
    html = _BANNER.sub("<!-- banner -->", html)
    html = _FOOTER_VARIANT.sub("<code>variant</code>", html)
    html = _STAMP.sub("<stamp>", html)
    html = _CLASS_VALUE.sub('class="hook"', html)
    return _STYLE_BLOCK.sub(
        lambda m: "<style>" + _CSS_SELECTOR.sub(".hook", m.group(1)) + "</style>", html)


# --------------------------------------------------------------------------------------

def check_adversarial(baseline: dict, baseline_count: int, clean_rows: list[dict],
                      verbose: bool) -> int:
    """Assert each adversarial page is shaped the way its hypothesis needs. Returns failure count."""
    results: list[tuple[bool, str, str, str]] = []   # ok, page, claim, evidence

    def claim(ok: bool, page: str, text: str, evidence: str = "") -> None:
        results.append((bool(ok), page, text, evidence))

    def verdict_for(rows: list[dict]) -> tuple[str, str]:
        v = decide(run_all_checks(baseline, rows, baseline_count))
        codes = ", ".join(sorted({f.code for f in v.failures})) or "-"
        return f"{v.decision.upper()} {v.confidence}/100", codes

    by_name = {r["name"]: r for r in clean_rows}

    # --- P1 ---------------------------------------------------------------------------
    p1 = render(rows_for("first_tile_anomaly"), "first_tile_anomaly")
    tiles = _ITEM.findall(p1)
    first, rest = (tiles[0], tiles[1:]) if tiles else ("", [])

    claim(len(tiles) == 30, "P1", "30 tiles render", f"got {len(tiles)}")
    claim("price-was" not in first and "price-ship" not in first, "P1",
          "tile 1 carries no crossed-out price and no delivery line")
    claim(all("price-was" in t and "price-ship" in t for t in rest), "P1",
          "tiles 2-30 all carry both",
          f"{sum(1 for t in rest if 'price-was' in t and 'price-ship' in t)}/29")
    claim(sum(1 for t in tiles if "price-ship" not in t) == 1, "P1",
          "tile 1 is the ONLY structural outlier")

    pos, sem = _p1_positional(p1), _p1_semantic(p1)
    claim(pos[0]["price"] == sem[0]["price"] == by_name[pos[0]["name"]]["price"], "P1",
          "both readings agree on tile 1 - so the one-row preview looks clean",
          f"${pos[0]['price']:,.2f}")
    claim(all(r["price"] == by_name[r["name"]]["price"] for r in sem), "P1",
          "semantic reading recovers all 30 clean prices - the page IS winnable")
    wrong = [r for r in pos[1:] if r["price"] == by_name[r["name"]]["shipping"]]
    claim(len(wrong) == 29, "P1",
          "positional reading lands on the delivery charge for tiles 2-30", f"{len(wrong)}/29")

    dec, codes = verdict_for(pos)
    claim("COLUMN_SWAP" in codes, "P1", f"positional reading -> {dec}", codes)
    dec, codes = verdict_for(sem)
    claim("COLUMN_SWAP" not in codes, "P1", f"semantic reading  -> {dec}", codes)

    # --- P2 ---------------------------------------------------------------------------
    p2 = render(rows_for("label_stripped"), "label_stripped")
    tiles = _ITEM.findall(p2)
    pairs = [_MONEY_SPAN.findall(t) for t in tiles]

    claim(all(len(p) == 2 for p in pairs), "P2", "every tile has exactly two money nodes")
    claim(all(_MONEY_PAIR.search(t) for t in tiles), "P2",
          "the two are adjacent siblings, nothing but whitespace between them")
    claim(all(len(p) == 2 and p[0][0].replace(p[0][1], "") == p[1][0].replace(p[1][1], "")
              for p in pairs), "P2",
          "delete the digits and the two nodes are the same string")
    claim(all(_BARE_MONEY.match(text.strip()) for pair in pairs for _, text in pair), "P2",
          "neither node carries any text label at all")
    claim("Shipping" not in p2, "P2", "the word 'Shipping' appears nowhere on the page")
    claim(p2.count(".money {") == 1, "P2", "both nodes are styled by one rule, so neither looks big")

    order, magnitude = _p2_rows(p2, by_magnitude=False), _p2_rows(p2, by_magnitude=True)
    claim(all(r["price"] == by_name[r["name"]]["price"] for r in magnitude), "P2",
          "reading by magnitude recovers all 30 clean prices - the page IS winnable")
    claim(all(r["price"] == by_name[r["name"]]["shipping"] for r in order), "P2",
          "reading by order lands on the delivery charge on all 30")
    ratios = [by_name[r["name"]]["price"] / by_name[r["name"]]["shipping"] for r in order]
    claim(min(ratios) > 10, "P2", "magnitude is a usable discriminator on every tile",
          f"smallest gap {min(ratios):.0f}x")

    dec, codes = verdict_for(order)
    claim("COLUMN_SWAP" in codes, "P2", f"reading by order     -> {dec}", codes)
    dec, codes = verdict_for(magnitude)
    claim("COLUMN_SWAP" not in codes, "P2", f"reading by magnitude -> {dec}", codes)

    # --- P3 ---------------------------------------------------------------------------
    before = render(rows_for("renamed_dom_before"), "renamed_dom_before")
    after = render(rows_for("renamed_dom_after"), "renamed_dom_after")

    claim(_blank_hooks(before) == _blank_hooks(after), "P3",
          "before and after differ in class names and in NOTHING else")
    shared = _hooks(before) & _hooks(after)
    claim(not shared, "P3", "no class name survives the rename - every hook is stale",
          f"{len(_hooks(before))} old, {len(_hooks(after))} new, {len(shared)} shared")
    claim(parse(after) == [], "P3",
          "the old selectors return zero rows against the new page - the break is total")
    claim(_parse_renamed(after) == parse(before), "P3",
          "the new selectors return byte-identical values - nothing but names moved",
          f"{len(_parse_renamed(after))} rows")
    claim("out of 5" in after and after.count("out of 5") == 30, "P3",
          "the rename touched hooks only, not the prose it shares words with")

    dec, codes = verdict_for(_parse_renamed(after))
    claim(codes == "-", "P3", f"the renamed page, read correctly -> {dec}", codes)

    # --- report -----------------------------------------------------------------------
    width = max(len(text) for _, _, text, _ in results)
    for ok, page, text, evidence in results:
        mark = "OK  " if ok else "FAIL"
        tail = f"  ({evidence})" if evidence and (verbose or not ok) else ""
        print(f"[{mark}] {page}  {text:{width}}{tail}")

    return sum(1 for ok, *_ in results if not ok)


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
    else:
        print(f"all {len(VARIANTS)} variants trip the check they were designed to trip")

    print()
    print(f"adversarial pages ({len(ADVERSARIAL)} variants, 3 files) - proving the FIXTURE:")
    print()
    broken = check_adversarial(baseline, baseline_count, clean_rows, args.verbose)
    print()
    if broken:
        print(f"{broken} claim(s) about the adversarial pages are not true of the rendered HTML.")
        print("Fix the page before spending a credit: an unfair fixture cannot convict a healer.")
    else:
        print("every adversarial page is shaped as claimed - each has a reachable right answer")
        print("and a reachable wrong one, so a live failure cannot be blamed on the markup")

    return 1 if (failures or broken) else 0


if __name__ == "__main__":
    raise SystemExit(main())
