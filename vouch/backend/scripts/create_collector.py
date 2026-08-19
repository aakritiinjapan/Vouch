"""
Create the live Scraper Studio collector, run it once, and wire it into the app.

This is the step the hackathon rules require: a CUSTOM scraper built with Scraper Studio (a collector
pulled from the Scrapers Library does not qualify), plus a live c_* id and a committed sample of real
structured output.

    # from vouch/backend, with MOCK_MODE=false and a credential available
    python -m scripts.create_collector "https://example.com/listing" \\
        --fields "product name, current sale price, per-item shipping cost, rating, in stock" \\
        --name vouch-competitor

What it does, in order:
    1. `scraper create`  -> a c_* collector id
    2. `scraper run`     -> real rows
    3. writes docs/sample_output.json          (the submission's "example structured output")
    4. writes the Baseline row for that collector   (the guardian's reference point)
    5. points the seeded products at the new collector id
    6. tells you exactly what to paste into the README

Two things to know before you run it (both learned the hard way - see docs/BRIGHT_DATA_NOTES.md):

    The description is capped at 500 characters, and `create` provisions the collector BEFORE it
    starts AI generation. So an over-long description gets a 400 and still leaves a half-built
    collector on your account - which Bright Data exposes no way to delete programmatically. We
    validate the length locally now, but if any create fails, check
    https://brightdata.com/cp/scrapers and remove the orphan by hand.

    AI generation takes 5-10 minutes. Do not run this inside anything with a shorter wall-clock
    limit, or you lose the collector id from stdout while the job keeps running server-side.

On the field description: write it PRECISELY. This first run becomes the guardian's baseline, so an
ambiguous description here poisons the reference every later heal is judged against. The demo breaks
the scraper later with a deliberately vague HEAL prompt - never a vague create prompt. See
docs/DEMO_SCRIPT.md, technique C.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlmodel import select

from app.config import settings
from app.db import get_session, init_db
from app.models import Baseline, Product
from app.scraper import baseline as baseline_capture
from app.scraper import brightdata

DOCS = Path(__file__).resolve().parents[2] / "docs"

DEFAULT_FIELDS = (
    "for each product in the listing: the product name, its own current sale price, "
    "the per-item shipping or delivery cost, the average customer rating, and whether it is in stock"
)

# The guardian needs at least two numeric fields that could plausibly be confused for one another,
# or COLUMN_SWAP has nothing to compare and the whole demo loses its teeth.
WANTED_NUMERIC = 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="a PUBLIC competitor listing page (no login, no paywall)")
    parser.add_argument("--fields", default=DEFAULT_FIELDS,
                        help="natural-language description of the fields to extract")
    parser.add_argument("--name", default="vouch-competitor", help="collector name")
    parser.add_argument("--timeout", type=int, default=900,
                        help="AI generation polling timeout in seconds (docs say 5-10 min)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be sent to Bright Data and exit")
    return parser.parse_args(argv)


def _preflight() -> None:
    if settings.mock_mode:
        sys.exit(
            "MOCK_MODE is true, so this would create nothing real.\n"
            "Set MOCK_MODE=false in backend/.env before creating a live collector."
        )
    if not (settings.brightdata_api_key or settings.brightdata_api_token):
        print("! No BRIGHTDATA_API_KEY in .env - relying on `brightdata login` credentials.\n"
              "  If this fails, run: npx -y @brightdata/cli login", file=sys.stderr)


def _describe_rows(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Split the first row's keys into numeric-looking and other, for the sanity report."""
    from app.guardian.checks import profile_run

    profiles = profile_run(rows)
    numeric = [name for name, p in profiles.items() if p.dtype == "numeric"]
    other = [name for name in profiles if name not in numeric]
    return numeric, other


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.dry_run:
        print("would run: scraper create")
        print(f"  url    : {args.url}")
        print(f"  fields : {args.fields}")
        print(f"  name   : {args.name}")
        print(f"  chars  : {len(args.fields)} / {brightdata.MAX_DESCRIPTION_CHARS}")
        return

    _preflight()

    print(f"creating collector against {args.url} ...")
    collector_id = brightdata.create_collector(args.url, args.fields, name=args.name,
                                               timeout=args.timeout)
    print(f"  collector_id = {collector_id}")

    print("running it once to capture the baseline ...")
    rows = brightdata.run(collector_id, args.url)
    if not rows:
        sys.exit("The collector returned no rows. Refine --fields and try again; "
                 "a baseline cannot be built from an empty run.")
    print(f"  {len(rows)} rows")

    # --- sanity: does this page actually support the guardian's premise? -------------------
    numeric, other = _describe_rows(rows)
    print(f"  numeric fields: {', '.join(numeric) or '(none)'}")
    print(f"  other fields  : {', '.join(other) or '(none)'}")
    if len(numeric) < WANTED_NUMERIC:
        print(f"\n! Only {len(numeric)} numeric field(s). COLUMN_SWAP compares one numeric field "
              f"against another, so with fewer than {WANTED_NUMERIC} the guardian's headline check "
              f"cannot fire. Consider a page that also shows shipping cost, or a crossed-out "
              f"original price alongside the sale price.", file=sys.stderr)

    # --- the submission's example structured output ----------------------------------------
    DOCS.mkdir(parents=True, exist_ok=True)
    sample_path = DOCS / "sample_output.json"
    sample_path.write_text(json.dumps({
        "_comment": (
            "Real structured output from the Vouch collector, captured by "
            "scripts/create_collector.py. This is the run that became the guardian's baseline."
        ),
        "collector_id": collector_id,
        "source_url": args.url,
        "field_description": args.fields,
        "rows": rows,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {sample_path.relative_to(DOCS.parents[1])}")

    # --- persist the baseline and repoint the seeded products ------------------------------
    init_db()
    with get_session() as session:
        profiles, count = baseline_capture.capture(rows)
        existing = session.exec(
            select(Baseline).where(Baseline.collector_id == collector_id)
        ).first()
        if existing is None:
            session.add(Baseline(collector_id=collector_id, record_count=count,
                                 field_profiles=profiles))
        else:
            existing.field_profiles, existing.record_count = profiles, count
            session.add(existing)

        products = list(session.exec(select(Product)))
        for product in products:
            product.collector_id = collector_id
            product.competitor_url = args.url
            session.add(product)
        session.commit()
        product_count = len(products)

    print(f"  baseline stored ({count} rows); {product_count} product(s) repointed")

    # --- what the human still has to do ---------------------------------------------------
    names = [str(r.get("name", "")) for r in rows if r.get("name")]
    print("\n" + "-" * 78)
    print("NEXT STEPS")
    print("-" * 78)
    print(f"1. README section 9 - replace the placeholder with:  {collector_id}")
    print(f"2. scripts/seed.py - set DEMO_COLLECTOR_ID = \"{collector_id}\"")
    if names:
        print("3. scripts/seed.py - DEMO_PRODUCTS names must match rows from this page, e.g.:")
        for name in names[:3]:
            print(f"     {name}")
        print("   (the seeder asserts this; a mismatch yields 'no confirmed competitor price')")
    print("4. Commit docs/sample_output.json")
    print("5. Try the heal, with a deliberately VAGUE prompt, e.g.:")
    print(f"     npx -y @brightdata/cli scraper heal {collector_id} \\")
    print("       \"the price field looks wrong, re-capture the price near the delivery info\"")
    print("   then confirm the envelope has status=awaiting_approval and a preview_result array.")
    print(f"6. Reject it so nothing is committed:")
    print(f"     npx -y @brightdata/cli scraper approve {collector_id} --reject")


if __name__ == "__main__":
    main()
