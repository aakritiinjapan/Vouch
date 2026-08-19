"""
Seed the demo products, their shared baseline, and enough price history for an honest chart.

Run:  python -m scripts.seed        (from backend/, with the venv active)

Idempotent: re-running updates the seeded products in place rather than duplicating them, so you can
seed as often as you like while iterating.

On the price history below: a pre-populated demo database is normal and honest - without it the chart
has two points and looks broken. What we will not do is invent continuity at RUNTIME,
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

# The real collector, created by scripts/create_collector.py against Newegg's GPU category page.
# All SKUs are read from that one listing page, so they legitimately share one collector - and
# therefore one baseline.
COLLECTOR_ID = "c_mszq0z1x27brru3wab"
LIVE_URL = "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96"

# Every name below is a row the live collector actually returned, verified to identify EXACTLY ONE
# row in that run. That matters: Newegg lists several near-identical variants of the same card, and
# orchestrator._extract_competitor_price correctly refuses to guess between them - so a name matching
# more than one row yields no price at all, which looks like a bug on stage.
#
# The first two carry $19.99 shipping in the real data, which is what makes the swap demo land: a
# heal that reads the shipping element instead of the price element reports that a $6,900 card now
# sells for $19.99. The third ships free, so the same swap reports $0.00 - the failure is total, and
# we show it that way rather than cherry-picking only the dramatic rows.
#
# Costs are illustrative; a real seller supplies their own. They are chosen so the floor sits
# meaningfully below the competitor price, which is what makes the counterfactual's clamp visible
# rather than academic.
DEMO_PRODUCTS = [
    dict(sku="GPU-5090-ZOTAC",
         name="ZOTAC ARCTICSTORM AIO GeForce RTX 5090 32GB GDDR7 PCI Express 5.0 x16 ATX Graphics "
              "Card RTX 5090 ARCTICSTORM AIO",
         my_price=6999.00, cost=5600.00, floor_margin=0.08, competitor_url=LIVE_URL),
    dict(sku="GPU-5090-MSI",
         name="MSI Gaming GeForce RTX 5090 32GB GDDR7 PCI Express 5.0 Graphics Card RTX 5090 32G "
              "GAMING TRIO OC",
         my_price=4779.00, cost=3820.00, floor_margin=0.08, competitor_url=LIVE_URL),
    dict(sku="GPU-5090-ASUS",
         name="ASUS ROG Astral GeForce RTX 5090 32GB GDDR7 OC Edition ROG-ASTRAL-RTX5090-O32G-"
              "GAMING DLSS 4.0 PCI Express 5.0 Graphics Card",
         my_price=4899.00, cost=3900.00, floor_margin=0.10, competitor_url=LIVE_URL),
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
            f"Product.name must match a 'name' in the active dataset "
            f"(tests/fixtures/{settings.demo_dataset}.json) exactly."
        )


def _upsert_products(session, specs: list[dict], collector_id: str) -> list[Product]:
    products = []
    for spec in specs:
        existing = session.exec(select(Product).where(Product.sku == spec["sku"])).first()
        if existing is None:
            existing = Product(**spec, collector_id=collector_id,
                               seed_price=spec["my_price"])
        else:
            for key, value in spec.items():
                setattr(existing, key, value)
            existing.collector_id = collector_id
            existing.seed_price = spec["my_price"]
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
    parser.parse_args(argv)

    init_db()
    specs = DEMO_PRODUCTS
    rows = _fixture("baseline")
    _assert_names_match_fixture(specs, rows)

    with get_session() as session:
        products = _upsert_products(session, specs, COLLECTOR_ID)
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
    print(f"products        {product_count} seeded/updated (collector {COLLECTOR_ID})")
    print(f"price history   {history} observations written")
    print(f"baseline        id={baseline_id}, {baseline_rows} rows, fields: {', '.join(profiles)}")
    print(f"mock mode       {settings.mock_mode}")


if __name__ == "__main__":
    main()
