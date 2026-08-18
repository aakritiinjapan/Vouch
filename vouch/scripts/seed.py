"""
Seed a handful of demo products so the dashboard has something to show.

Run:  python -m scripts.seed   (from backend/, with the venv active)

For the live-heal demo you also need a competitor page you can break on cue. The most reliable
approach (see docs/DEMO_SCRIPT.md): take a snapshot of a real product-listing page's HTML, host it
as a static "v1" page, then deploy a "v2" with the price markup moved and a shipping-cost element
placed where a naive heal is likely to grab it. Point propose_heal at the v2 URL during the demo.
"""

from __future__ import annotations

from app.db import get_session, init_db
from app.models import Product
from app.scraper import baseline
from app.scraper.brightdata import _fixture  # baseline rows for the demo profile


DEMO_PRODUCTS = [
    dict(sku="GPU-5080-MSI", name="MSI RTX 5080 Gaming Trio", my_price=1319.00, cost=1050.00,
         floor_margin=0.08, competitor_url="https://example.com/newegg-mirror/rtx-5080-msi"),
    dict(sku="GPU-5090-ASUS", name="ASUS ROG Astral RTX 5090", my_price=2049.00, cost=1650.00,
         floor_margin=0.08, competitor_url="https://example.com/newegg-mirror/rtx-5090-asus"),
    dict(sku="GPU-5070-ASUS", name="ASUS Prime RTX 5070", my_price=619.00, cost=470.00,
         floor_margin=0.10, competitor_url="https://example.com/newegg-mirror/rtx-5070-asus"),
]


def main() -> None:
    init_db()
    with get_session() as s:
        for p in DEMO_PRODUCTS:
            s.add(Product(**p))
        s.commit()
    profiles, count = baseline.capture(_fixture("baseline"))
    print(f"Seeded {len(DEMO_PRODUCTS)} products. Baseline profile captured for {count} rows.")
    print("Fields profiled:", ", ".join(profiles.keys()))
    # Claude Code: also persist a Baseline row per collector_id once collectors exist.


if __name__ == "__main__":
    main()
