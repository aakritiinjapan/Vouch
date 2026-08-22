#!/usr/bin/env python3
"""
Generate the Voltmart test storefront - a page we control, so a heal can be broken on purpose.

Detection in this repo is otherwise only ever proven against MUTATED FIXTURES: we take real Newegg
rows and corrupt them in Python. That proves the checks work on the data, but it never proves the
loop works against Bright Data - a real collector reading a really-broken page. This page closes
that gap. Point a Scraper Studio collector at the clean variant to capture a baseline, regenerate as
a broken variant, redeploy, then heal: every verdict after that is earned end to end.

    python generate.py                 # clean baseline -> index.html
    python generate.py --variant swap  # price and shipping trade places
    python generate.py --list          # every variant and the check it should trip

The numbers are chosen, not random. Three things the real Newegg page cannot give us:

  * shipping is NONZERO AND VARYING ($4.99-$24.99). On the live Newegg category page shipping is
    "Free Shipping" on 90 of 92 tiles, so the flagship price-into-shipping swap has no distribution
    to land on. Here it does.
  * the three numeric fields are FAR APART - price ~$700, shipping ~$15, rating ~4.3. check_column_swap
    refuses to call a swap between fields that were not distinguishable at baseline (its third guard),
    so a testbed needs the separation to be unmistakable.
  * original_price sits only 5-30% above price. That is deliberately INSIDE check_column_swap's blind
    spot - too close to move a median, too similar to claim a swap - which is the exact case
    check_value_ordering exists for. Both checks get a real target on one page.
"""

from __future__ import annotations

import argparse
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "index.html"

SEED = 20260822  # fixed, so the clean baseline is byte-identical on every regeneration

# (name, price, original_price or None, shipping, rating, in_stock)
# Written out rather than generated so a human can read the baseline and edit one row by hand.
PRODUCTS: list[tuple[str, float, float | None, float, float, bool]] = [
    ("Voltmart RTX 5090 Founders Edition 32GB GDDR7",      1999.99, 2199.99, 24.99, 4.8, True),
    ("Voltmart RTX 5080 Stormbringer 16GB GDDR7",          1149.99, 1279.99, 19.99, 4.6, True),
    ("Voltmart RTX 5070 Ti Aero 16GB GDDR7",                849.99,  899.99, 14.99, 4.5, True),
    ("Voltmart RTX 5070 Pulse 12GB GDDR7",                  629.99,  689.99, 14.99, 4.3, True),
    ("Voltmart RTX 5060 Ti Windforce 16GB",                 449.99,  479.99,  9.99, 4.2, True),
    ("Voltmart RTX 5060 Eagle 8GB",                         329.99,     None,  9.99, 4.0, True),
    ("Voltmart RX 9070 XT Nitro+ 16GB",                     749.99,  819.99, 16.99, 4.4, True),
    ("Voltmart RX 9070 Hellhound 16GB",                     659.99,  699.99, 16.99, 4.1, True),
    ("Voltmart RX 9060 XT Pulse 16GB",                      389.99,  429.99, 12.49, 3.9, True),
    ("Voltmart RX 9060 Challenger 8GB",                     279.99,     None, 12.49, 3.7, False),
    ("Voltmart Arc B770 Limited 16GB",                      369.99,  399.99, 11.99, 3.8, True),
    ("Voltmart Arc B750 Challenger 12GB",                   249.99,     None, 11.99, 3.6, True),
    ("Voltmart RTX 5090 Titan Liquid 32GB",                2449.99, 2599.99, 24.99, 4.9, False),
    ("Voltmart RTX 5080 Suprim Liquid X 16GB",             1349.99, 1449.99, 22.99, 4.7, True),
    ("Voltmart RTX 5070 Ti Gaming Trio 16GB",               899.99,  949.99, 14.99, 4.4, True),
    ("Voltmart RTX 4090 Gaming OC 24GB",                   1799.99, 1949.99, 21.99, 4.8, False),
    ("Voltmart RTX 4080 Super Ventus 16GB",                 999.99, 1099.99, 18.49, 4.5, True),
    ("Voltmart RTX 4070 Ti Super Dual 16GB",                719.99,  779.99, 15.49, 4.3, True),
    ("Voltmart RTX 4060 Ti Low Profile 8GB",                379.99,  409.99,  8.99, 4.0, True),
    ("Voltmart RX 7900 XTX Taichi 24GB",                    929.99,  999.99, 19.49, 4.6, True),
    ("Voltmart RX 7900 GRE Steel Legend 16GB",              549.99,  589.99, 15.99, 4.2, True),
    ("Voltmart RX 7800 XT Phantom 16GB",                    489.99,     None, 13.99, 4.1, True),
    ("Voltmart RX 7700 XT Fighter 12GB",                    409.99,  439.99, 13.99, 3.9, False),
    ("Voltmart RX 7600 XT Swift 16GB",                      309.99,  329.99, 10.99, 3.8, True),
    ("Voltmart GTX 1660 Super Refresh 6GB",                 179.99,     None,  6.99, 3.5, True),
    ("Voltmart Quadro A2000 Workstation 12GB",              649.99,  699.99, 17.99, 4.4, True),
    ("Voltmart Radeon Pro W7600 8GB",                       579.99,  619.99, 16.49, 4.2, True),
    ("Voltmart Arc A770 Predator 16GB",                     289.99,  319.99, 10.49, 3.7, True),
    ("Voltmart RTX 5050 Verto Dual 8GB",                    249.99,  269.99,  7.99, 3.6, True),
    ("Voltmart GT 1030 Silent Passive 2GB",                  89.99,     None,  4.99, 3.2, True),
]


# --------------------------------------------------------------------------------------
# Variants - each one breaks exactly one thing, so the verdict names one root cause
# --------------------------------------------------------------------------------------

VARIANTS: dict[str, str] = {
    "clean":    "the honest page - capture the baseline from this",
    "swap":     "price and shipping trade places        -> COLUMN_SWAP (critical)",
    "inverted": "price and original_price trade places  -> VALUE_ORDER_INVERTED (critical)",
    "nulls":    "price blanked on 70% of rows           -> NULL_SPIKE (high)",
    "missing":  "the shipping column is removed         -> FIELD_MISSING (critical)",
    "collapse": "every name pinned to one string        -> CARDINALITY_COLLAPSE (medium)",
    "instock":  "in_stock forced false everywhere       -> BOOL_RATIO_SHIFT (medium)",
    "drift":    "price AND original_price inflated 4x   -> NUMERIC_DRIFT (high)",
}


def apply_variant(rows: list[dict], variant: str) -> list[dict]:
    """Corrupt the rows the way a bad heal would. One root cause per variant, never two."""
    rng = random.Random(SEED)
    out = [dict(r) for r in rows]

    if variant == "clean":
        return out

    if variant == "swap":
        # The classic. The heal starts reading the delivery line into the price element.
        for r in out:
            r["price"], r["shipping"] = r["shipping"], r["price"]
        return out

    if variant == "inverted":
        # The subtle one: the crossed-out reference price lands in `price`. Only 5-30% off, so no
        # median moves far enough to trip drift - only the ordering invariant catches it.
        for r in out:
            if r["original_price"] is not None:
                r["price"], r["original_price"] = r["original_price"], r["price"]
        return out

    if variant == "nulls":
        # A selector that matches on some layouts and not others.
        for r in out:
            if rng.random() < 0.7:
                r["price"] = None
        return out

    if variant == "missing":
        for r in out:
            r["shipping"] = None
        return out

    if variant == "collapse":
        # Pinned to a static element - the scraper reads the page heading for every row.
        for r in out:
            r["name"] = "Graphics Cards"
        return out

    if variant == "instock":
        # Forced FALSE, not true. The baseline is already 87% in stock, so pinning everything to
        # `true` moves the ratio by only 0.13 - under check_bool_ratio's 0.5 threshold, and rightly
        # so. Pinning to `false` moves it 0.87, which is what a lost stock selector actually looks
        # like: the element is missing, so nothing reads as in stock.
        for r in out:
            r["in_stock"] = False
        return out

    if variant == "drift":
        # Both prices scale together. Inflating `price` alone also pushes it above `original_price`
        # on every row, so check_value_ordering fires CRITICAL and wins the primary slot - two root
        # causes from one edit, which defeats the point of a single-cause variant. Scaling the pair
        # keeps the ordering valid and isolates the drift, the way a scraper that starts reading a
        # multi-pack or tax-inclusive total would.
        for r in out:
            if r["price"] is not None:
                r["price"] = round(r["price"] * 4, 2)
            if r["original_price"] is not None:
                r["original_price"] = round(r["original_price"] * 4, 2)
        return out

    raise ValueError(f"unknown variant {variant!r}; choose from {', '.join(VARIANTS)}")


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------

def _money(v: float | None) -> str:
    return "" if v is None else f"${v:,.2f}"


def _card(r: dict, drop_shipping: bool) -> str:
    """One product tile.

    Every scraped value gets its own class and sits in its own element. That is not decoration - a
    collector built from a natural-language description needs an unambiguous anchor per field, and
    a tile whose price and delivery line are adjacent is exactly what makes the swap plausible.
    """
    was = (f'<span class="price-was">{_money(r["original_price"])}</span>'
           if r["original_price"] is not None else "")
    ship = "" if drop_shipping else (
        f'<div class="price-ship">{_money(r["shipping"])} Shipping</div>')
    stock = ('<span class="stock in">In Stock</span>' if r["in_stock"]
             else '<span class="stock out">Out of Stock</span>')
    price = _money(r["price"]) or "&mdash;"

    return f"""      <li class="item">
        <a class="item-title" href="/p/{r['slug']}">{r['name']}</a>
        <div class="item-rating"><span class="rating">{r['rating']:.1f}</span> out of 5</div>
        <div class="item-price">
          <span class="price-current">{price}</span>
          {was}
        </div>
        {ship}
        <div class="item-stock">{stock}</div>
      </li>"""


STYLE = """    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0; background: #0d0f14; color: #e8eaf0;
      font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    header {
      border-bottom: 1px solid #23262f; padding: 18px 28px;
      display: flex; align-items: baseline; gap: 14px;
    }
    .brand { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
    .brand span { color: #7c5cff; }
    .tagline { color: #8b90a0; font-size: 13px; }
    main { max-width: 1180px; margin: 0 auto; padding: 26px 28px 60px; }
    h1 { font-size: 19px; font-weight: 600; margin: 0 0 4px; }
    .count { color: #8b90a0; font-size: 13px; margin-bottom: 22px; }
    ul.grid {
      list-style: none; margin: 0; padding: 0; display: grid; gap: 14px;
      grid-template-columns: repeat(auto-fill, minmax(258px, 1fr));
    }
    .item {
      background: #14171e; border: 1px solid #23262f; border-radius: 10px;
      padding: 15px 16px 14px; display: flex; flex-direction: column; gap: 7px;
    }
    .item-title {
      color: #e8eaf0; text-decoration: none; font-weight: 500; font-size: 14px;
      line-height: 1.35; min-height: 38px;
    }
    .item-title:hover { color: #a08cff; }
    .item-rating { color: #8b90a0; font-size: 12px; }
    .rating { color: #ffc857; font-weight: 600; }
    .item-price { display: flex; align-items: baseline; gap: 9px; margin-top: 2px; }
    .price-current { font-size: 21px; font-weight: 700; letter-spacing: -0.02em;
      font-variant-numeric: tabular-nums; }
    .price-was { color: #8b90a0; text-decoration: line-through; font-size: 13px;
      font-variant-numeric: tabular-nums; }
    .price-ship { color: #6fd39a; font-size: 12.5px; font-variant-numeric: tabular-nums; }
    .item-stock { margin-top: 3px; }
    .stock { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.06em;
      padding: 2px 7px; border-radius: 5px; }
    .stock.in { color: #6fd39a; background: rgba(111,211,154,0.11); }
    .stock.out { color: #ff7a7a; background: rgba(255,122,122,0.11); }
    footer { border-top: 1px solid #23262f; margin-top: 46px; padding: 18px 28px;
      color: #6a6f7e; font-size: 12px; }
    code { color: #a08cff; font-family: ui-monospace, "JetBrains Mono", monospace; }"""


def render(rows: list[dict], variant: str) -> str:
    drop_shipping = variant == "missing"
    cards = "\n".join(_card(r, drop_shipping) for r in rows)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note = VARIANTS[variant]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Voltmart &mdash; Graphics Cards</title>
  <!--
    A TEST FIXTURE, not a real shop. Every product, price and rating on this page is invented.
    Generated by vouch/testbed/generate.py  ·  variant: {variant}  ·  {stamp}
    {note}
  -->
  <meta name="robots" content="noindex, nofollow">
  <meta name="generator" content="vouch-testbed">
  <style>
{STYLE}
  </style>
</head>
<body>
  <header>
    <div class="brand">Volt<span>mart</span></div>
    <div class="tagline">test fixture for Vouch &mdash; every price here is invented</div>
  </header>

  <main>
    <h1>Graphics Cards</h1>
    <div class="count">{len(rows)} products</div>

    <ul class="grid">
{cards}
    </ul>
  </main>

  <footer>
    Synthetic data for validating scraper self-heals. Variant <code>{variant}</code>,
    generated {stamp}. Not a real storefront; nothing here is for sale.
  </footer>
</body>
</html>
"""


def _slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def base_rows() -> list[dict]:
    return [
        {"name": n, "price": p, "original_price": o, "shipping": s,
         "rating": r, "in_stock": k, "slug": _slug(n)}
        for n, p, o, s, r, k in PRODUCTS
    ]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="clean", choices=sorted(VARIANTS))
    ap.add_argument("--out", default=str(OUT), help="where to write the HTML")
    ap.add_argument("--list", action="store_true", help="list the variants and exit")
    args = ap.parse_args(argv)

    if args.list:
        width = max(len(v) for v in VARIANTS)
        for name, desc in VARIANTS.items():
            print(f"  {name:{width}}  {desc}")
        return

    rows = apply_variant(base_rows(), args.variant)
    html = render(rows, args.variant)
    path = Path(args.out)
    path.write_text(html, encoding="utf-8")

    priced = [r["price"] for r in rows if r["price"] is not None]
    print(f"wrote {path}  ({len(html):,} bytes)")
    print(f"  variant : {args.variant} - {VARIANTS[args.variant]}")
    print(f"  products: {len(rows)}, {len(priced)} with a price")
    if priced:
        # statistics.median, matching what the guardian's profiler computes - picking the upper of
        # the two middle values instead would print a different number here than verify.py reports
        # for the same page, which is a confusing thing to hand someone.
        print(f"  price   : median ${statistics.median(priced):,.2f}")


if __name__ == "__main__":
    main()
