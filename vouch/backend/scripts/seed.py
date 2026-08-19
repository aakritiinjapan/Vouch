"""
Seed the demo products, their shared baseline, and enough price history for an honest chart.

Run:  python -m scripts.seed        (from backend/, with the venv active)

Idempotent: re-running updates the seeded products in place rather than duplicating them, so you can
seed as often as you like while iterating.

On the price history below: a pre-populated demo database is normal and honest - without it the chart
has two points and looks broken. What README section 7 forbids is inventing continuity at RUNTIME,
i.e. drawing a straight line across a cycle whose source the guardian could not confirm. These rows
are real observations we are stating up front are seed data; the gap the demo punches in them later
is real.

For the live-heal demo you need a competitor page you can break on cue. See docs/DEMO_SCRIPT.md - the
technique we use creates the collector with a PRECISE description (so the first extraction is correct
and becomes the baseline), then heals it with a deliberately vague prompt so the heal grabs the wrong
column. Underspecifying the *create* step instead would make the bad data the baseline, and the
guardian would then flag the correct fix as the drift.
"""

from __future__ import annotations

import argparse
from datetime import timedelta

from sqlmodel import select

from app.config import settings
from app.db import get_session, init_db
from app.models import CompetitorObservation, Product, _now
from app.scraper import baseline as baseline_capture
from app.scraper.brightdata import _fixture

# All SKUs are read from one competitor listing page, so they legitimately share one collector - and
# therefore one baseline.
DEMO_COLLECTOR_ID = "c_mock_newegg_gpu"

# The real collector, created by scripts/create_collector.py against Newegg's GPU category page.
LIVE_COLLECTOR_ID = "c_mszq0z1x27brru3wab"
LIVE_URL = "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96"

# Two product sets, because the two modes match against different data and neither should pretend to
# be the other:
#
#   DEMO_PRODUCTS names match tests/fixtures/sample_runs.json, which is labelled demo data.
#   LIVE_PRODUCTS names match rows the real collector actually returned (see docs/sample_output.json).
#
# Every LIVE name below was verified to identify EXACTLY ONE row in that run. That matters: Newegg
# lists four near-identical "MSI Ventus GeForce RTX 5070 Ti" variants at $1179.99, $1698 and
# $1199.99, and orchestrator._extract_competitor_price correctly refuses to guess between them - so a
# name that matches several rows yields no price at all, which looks like a bug on stage.
DEMO_PRODUCTS = [
    dict(sku="GPU-5080-MSI", name="MSI RTX 5080 Gaming Trio", my_price=1319.00, cost=1050.00,
         floor_margin=0.08, competitor_url="https://example.com/newegg-mirror/rtx-5080-msi"),
    dict(sku="GPU-5090-ASUS", name="ASUS ROG Astral RTX 5090", my_price=2049.00, cost=1650.00,
         floor_margin=0.08, competitor_url="https://example.com/newegg-mirror/rtx-5090-asus"),
    dict(sku="GPU-5070-ASUS", name="ASUS Prime RTX 5070", my_price=619.00, cost=470.00,
         floor_margin=0.10, competitor_url="https://example.com/newegg-mirror/rtx-5070-asus"),
]

# Costs are illustrative - a real seller would supply their own. Chosen so the floor sits meaningfully
# below the competitor price, which is what makes the counterfactual's clamp visible.
LIVE_PRODUCTS = [
    dict(sku="GPU-5080-AERO", name="GIGABYTE AERO GeForce RTX 5080",
         my_price=1779.00, cost=1420.00, floor_margin=0.08, competitor_url=LIVE_URL),
    dict(sku="GPU-5080-AORUS", name="GIGABYTE AORUS GeForce RTX 5080",
         my_price=1629.00, cost=1300.00, floor_margin=0.08, competitor_url=LIVE_URL),
    dict(sku="GPU-5080-SHADOW", name="MSI SHADOW GeForce RTX 5080",
         my_price=1609.00, cost=1285.00, floor_margin=0.10, competitor_url=LIVE_URL),
]

# eight days of plausible competitor movement, as a multiplier on the fixture's price
HISTORY_DRIFT = [1.035, 1.028, 1.019, 1.024, 1.012, 1.008, 1.003, 1.000]


def _assert_names_match_fixture(products: list[dict], rows: list[dict]) -> None:
    """orchestrator._extract_competitor_price matches on exact (case-folded) name.

    Renaming a product here without renaming the fixture row yields "no confirmed competitor price",
    which presents as a mysteriously empty queue rather than as an error. Fail loudly instead.
    """
    fixture_names = {str(r.get("name", "")).strip().lower() for r in rows}
    missing = [p["sku"] for p in products
               if p["name"].strip().lower() not in fixture_names]
    if missing:
        raise SystemExit(
            f"seed aborted: no fixture row matches the product name for {', '.join(missing)}.\n"
            f"Product.name must match a 'name' in tests/fixtures/sample_runs.json exactly."
        )


def _upsert_products(session, specs: list[dict], collector_id: str) -> list[Product]:
    products = []
    for spec in specs:
        existing = session.exec(select(Product).where(Product.sku == spec["sku"])).first()
        if existing is None:
            existing = Product(**spec, collector_id=collector_id)
        else:
            for key, value in spec.items():
                setattr(existing, key, value)
            existing.collector_id = collector_id
        existing.updated_at = _now()
        session.add(existing)
        products.append(existing)
    session.commit()
    for product in products:
        session.refresh(product)
    return products


def _seed_history(session, products: list[Product], rows: list[dict]) -> int:
    """Give each product a confirmed price history, unless it already has one."""
    by_name = {str(r.get("name", "")).strip().lower(): r for r in rows}
    written = 0
    now = _now()

    for product in products:
        already = session.exec(
            select(CompetitorObservation)
            .where(CompetitorObservation.product_id == product.id)
        ).first()
        if already is not None:
            continue

        row = by_name[product.name.strip().lower()]
        base_price = float(row["price"])
        for days_ago, drift in enumerate(reversed(HISTORY_DRIFT)):
            session.add(CompetitorObservation(
                product_id=product.id,
                observed_price=round(base_price * drift, 2),
                source_url=product.competitor_url,
                run_id="seed",
                confirmed=True,
                created_at=now - timedelta(days=days_ago + 1),
            ))
            written += 1

    session.commit()
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true",
                        help="seed the products that match the REAL collector's rows, and point them "
                             "at it, instead of the fixture-matching demo products")
    args = parser.parse_args(argv)

    init_db()
    specs = LIVE_PRODUCTS if args.live else DEMO_PRODUCTS
    collector_id = LIVE_COLLECTOR_ID if args.live else DEMO_COLLECTOR_ID
    rows = _fixture("baseline")

    if args.live:
        # Against the live collector the fixture is not the reference, so there is nothing to assert
        # here - create_collector.py already verified these names resolve to exactly one row each.
        print("! seeding LIVE products against the real collector."
              " MOCK_MODE must be false to run cycles against them.")
        print()
    else:
        _assert_names_match_fixture(specs, rows)

    with get_session() as session:
        products = _upsert_products(session, specs, collector_id)
        product_count = len(products)
        history = _seed_history(session, products, rows)

        # Persist the baseline the guardian validates every heal against. Imported lazily so this
        # script does not depend on the service layer's error types just to bootstrap.
        from app import service
        baseline = service.ensure_baseline(session, products[0], records=rows)
        session.commit()
        # Read everything we want to report while the objects are still attached to the session.
        baseline_id, baseline_rows = baseline.id, baseline.record_count

    profiles, _ = baseline_capture.capture(rows)
    print(f"database        {settings.database_url}")
    print(f"products        {product_count} seeded/updated (collector {collector_id})")
    print(f"price history   {history} observations written")
    print(f"baseline        id={baseline_id}, {baseline_rows} rows, fields: {', '.join(profiles)}")
    print(f"mock mode       {settings.mock_mode}")


if __name__ == "__main__":
    main()
