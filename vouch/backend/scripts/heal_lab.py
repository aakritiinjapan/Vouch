r"""
Run many real heals against one collector and record what the healer actually grabbed.

The question this exists to answer: does Bright Data's self-heal fail in a PATTERN? You cannot answer
that from the fixtures in this repo. Every wrong heal in tests/fixtures/*.json and in the testbed
generator was written by us in Python, so it reveals what we chose to write and nothing about the
healer. And the three real heals we have on record all extracted the correct field - including the
deliberately vague one - so the honest sample of observed Bright Data failures is currently ZERO.

This harness gathers the sample. For each attempt it drives a real `scraper heal`, catches the
approval gate, classifies WHICH baseline field the healer's output actually looks like, rejects so
nothing is committed, and appends one JSON line. Run it enough times across prompt families and a
pattern either appears in the tally or it does not.

    # from vouch/backend - gather (slow: each heal is a real 5-10 min AI job)
    MOCK_MODE=false python -m scripts.heal_lab --collector c_xxx --url https://site/ --repeat 2

    # then read the tally, offline and free
    python -m scripts.heal_lab --analyse

Every attempt is REJECTED, always, so the collector is left exactly as it was and the run is
repeatable. Deliberately serial: AI-Flow caps concurrent create/heal at 3 and a 4th returns 429.

Cost note: billing is per page load, so a single-page testbed is ~1-2 credits per heal while the
96-tile Newegg category page is ~97. Probe the cheap page.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.guardian.checks import (
    FieldProfile,
    _profile_distance,
    profile_run,
    run_all_checks,
)
from app.guardian.verdict import decide
from app.scraper import brightdata

DOCS = Path(__file__).resolve().parents[2] / "docs"
LOG = DOCS / "heal_lab.jsonl"

# Prompt families, each probing a different way an operator can be unclear. The point is not to find
# the single worst prompt but to see whether failures cluster by KIND of ambiguity.
#
# `misleading` is the load-bearing one. It is not ambiguous at all - it is clear and WRONG. If the
# healer obeys it, that tells us the healer trusts the prompt over the page, which is a far more
# useful finding than "vague prompts are risky": it means a confident operator can break a scraper
# in a way no amount of prompt hygiene would catch.
PROMPT_FAMILIES: dict[str, str] = {
    "control_sharp": (
        "The price field is wrong. Extract each product's own current selling price - the prominent "
        "price the customer pays - not the shipping cost and not any crossed-out reference price."
    ),
    "vague_generic": "the price field looks wrong, please fix it",
    "vague_positional": "the price field looks wrong, re-capture the price near the delivery info",
    "vague_nearby": "price is broken, take the number next to it instead",
    "misleading_crossed": (
        "The price field is wrong. The correct price is the crossed-out number shown above the "
        "current price."
    ),
    "misleading_shipping": (
        "The price field is wrong. The correct price is the delivery charge shown on each tile."
    ),
}


# A label is only claimed when the values genuinely SIT ON that field's distribution. This is
# check_column_swap's own `max_other_dist` guard, reused for the same reason it exists there: "nearest
# field" is not "that field". Without it, a heal that merely inflated the price 4x gets labelled
# `original_price` - because 4x the price happens to land nearer the higher field - and a phantom swap
# enters the tally. An instrument that manufactures the pattern it is looking for is worse than none.
MAX_LABEL_DISTANCE = 0.25


def _classify(rows: list[dict], baseline: dict[str, FieldProfile], field: str = "price") -> dict:
    """Which baseline field does the healer's `field` output actually resemble?

    This is the measurement, and every claim the lab makes rests on it. `check_column_swap` already
    asks exactly this question to decide whether a swap happened, so the same distance function and
    the same proximity threshold answer "what did it grab" - reused rather than reimplemented so the
    label and the verdict can never disagree.

    `looks_like` is None when no field is close enough to be named. That is a real answer, not a
    failure: it means the output resembles nothing we have seen, which is different from resembling
    something else.
    """
    proposed = profile_run(rows)
    prop = proposed.get(field)
    if prop is None or prop.dtype != "numeric" or prop.median is None:
        return {"looks_like": None, "reason": f"{field} is not numeric in the output",
                "median": None, "nearest": None, "distances": {}}

    numeric = {n: p for n, p in baseline.items() if p.dtype == "numeric" and p.median is not None}
    distances = {}
    for name, base in numeric.items():
        d = _profile_distance(prop, base)
        if d is not None:
            distances[name] = round(d, 4)
    if not distances:
        return {"looks_like": None, "reason": "no numeric baseline fields to compare",
                "median": prop.median, "nearest": None, "distances": {}}

    best = min(distances, key=lambda k: distances[k])
    if distances[best] > MAX_LABEL_DISTANCE:
        return {
            "looks_like": None,
            "reason": (f"no baseline field explains these values (nearest '{best}' at distance "
                       f"{distances[best]}, over the {MAX_LABEL_DISTANCE} threshold)"),
            "median": prop.median, "nearest": best, "distances": distances,
        }
    return {"looks_like": best, "reason": None, "median": prop.median,
            "nearest": best, "distances": distances}


def gather(args) -> None:
    if settings.mock_mode:
        sys.exit("MOCK_MODE is true - this would heal nothing real. Re-run with MOCK_MODE=false.")

    families = (args.prompts.split(",") if args.prompts else list(PROMPT_FAMILIES))
    unknown = [f for f in families if f not in PROMPT_FAMILIES]
    if unknown:
        sys.exit(f"unknown prompt families: {', '.join(unknown)}\n"
                 f"available: {', '.join(PROMPT_FAMILIES)}")

    print(f"collector : {args.collector}")
    print(f"url       : {args.url}")
    print(f"families  : {', '.join(families)}")
    print(f"repeat    : {args.repeat}  ->  {len(families) * args.repeat} real heals")
    print(f"est. time : {len(families) * args.repeat * 7} min (each heal is a 5-10 min AI job)")
    print(f"log       : {LOG}")
    print()

    # The baseline to classify against: whatever the collector returns right now, before any healing.
    print("capturing the current baseline (one run) ...")
    base_rows = brightdata.run(args.collector, args.url)
    baseline = profile_run(base_rows)
    print(f"  {len(base_rows)} rows, numeric fields: "
          f"{', '.join(n for n, p in baseline.items() if p.dtype == 'numeric')}")
    for name, p in baseline.items():
        if p.dtype == "numeric":
            print(f"    {name:16} median {p.median}")
    print()

    LOG.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    for rep in range(args.repeat):
        for family in families:
            prompt = PROMPT_FAMILIES[family]
            done += 1
            label = f"[{done}/{len(families) * args.repeat}] {family} rep{rep + 1}"
            print(f"{label}: healing ...", flush=True)

            record = {
                "at": datetime.now(timezone.utc).isoformat(),
                "collector_id": args.collector,
                "url": args.url,
                "family": family,
                "repetition": rep + 1,
                "prompt": prompt,
                "baseline_rows": len(base_rows),
            }
            started = time.monotonic()
            try:
                proposal = brightdata.propose_heal(args.collector, prompt, args.url)
                rows = proposal.proposed_records
                verdict = decide(run_all_checks(baseline, rows, len(base_rows),
                                                is_sample=proposal.is_sample))
                grabbed = _classify(rows, baseline)

                record.update({
                    "ok": True,
                    "seconds": round(time.monotonic() - started, 1),
                    "preview_rows": len(rows),
                    "extracted": rows[0] if rows else None,
                    "price_looks_like": grabbed["looks_like"],
                    "price_median": grabbed["median"],
                    "distances": grabbed["distances"],
                    "decision": verdict.decision,
                    "confidence": verdict.confidence,
                    "codes": sorted({f.code for f in verdict.failures}),
                })
                print(f"  -> {verdict.decision.upper()} {verdict.confidence}/100 · "
                      f"price looks like '{grabbed['looks_like']}' "
                      f"(median {grabbed['median']}) · {record['seconds']}s")
            except Exception as exc:  # noqa: BLE001 - one bad heal must not end the run
                record.update({"ok": False, "seconds": round(time.monotonic() - started, 1),
                               "error": f"{type(exc).__name__}: {exc}"})
                print(f"  -> FAILED: {record['error']}")

            # Always answer the gate, whatever happened, so the collector is never left waiting and
            # the next attempt starts from the same state as this one.
            try:
                brightdata.reject_heal(args.collector)
                record["rejected"] = True
            except Exception as exc:  # noqa: BLE001
                record["rejected"] = False
                record["reject_error"] = f"{type(exc).__name__}: {exc}"
                print(f"  !! could not reject: {record['reject_error']}")
                print("     answer the gate by hand before running again:")
                print(f"     npx -y @brightdata/cli scraper approve {args.collector} --reject")

            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

    print(f"\nwrote {done} attempts to {LOG.name}")
    print("now: python -m scripts.heal_lab --analyse")


def analyse(_args) -> None:
    if not LOG.exists():
        sys.exit(f"no {LOG.name} yet - run the gather mode first")

    records = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    ok = [r for r in records if r.get("ok")]
    print(f"attempts logged : {len(records)}  ({len(records) - len(ok)} errored)")
    if not ok:
        return

    print(f"collectors      : {', '.join(sorted({r['collector_id'] for r in ok}))}")
    print()

    # The headline: per prompt family, what did the healer actually grab?
    print("what the healer put in `price`, by prompt family")
    print(f"  {'family':22} {'n':>3}  {'grabbed':<34} decisions")
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in ok:
        by_family[r["family"]].append(r)

    for family in sorted(by_family):
        rs = by_family[family]
        grabbed = Counter(r.get("price_looks_like") or "?" for r in rs)
        decisions = Counter(r["decision"] for r in rs)
        g = ", ".join(f"{k}x{v}" for k, v in grabbed.most_common())
        d = ", ".join(f"{k}x{v}" for k, v in decisions.most_common())
        print(f"  {family:22} {len(rs):>3}  {g:<34} {d}")

    # Is the healer deterministic? Same prompt, same page, same answer?
    print()
    print("determinism: distinct medians returned per family")
    for family in sorted(by_family):
        medians = {r.get("price_median") for r in by_family[family]}
        n = len(by_family[family])
        verdict = "deterministic" if len(medians) == 1 else f"{len(medians)} distinct outcomes"
        print(f"  {family:22} {n:>3} run(s) -> {verdict}  {sorted(m for m in medians if m is not None)}")

    # Did anything actually go wrong? This is the number the question hangs on.
    wrong = [r for r in ok if r.get("price_looks_like") not in (None, "price")]
    print()
    print(f"heals that grabbed a field other than `price`: {len(wrong)} of {len(ok)}")
    if not wrong:
        print("  No observed Bright Data mis-heal in this sample. A pattern cannot be reported from")
        print("  zero events - say so plainly rather than reaching for the synthetic fixtures, which")
        print("  only show what we wrote.")
        return

    for r in wrong:
        print(f"  {r['family']:22} grabbed '{r['price_looks_like']}' "
              f"(median {r['price_median']}) · {r['decision'].upper()} {r['confidence']}/100 "
              f"· codes {','.join(r['codes']) or 'none'}")

    caught = [r for r in wrong if r["decision"] != "pass"]
    print()
    print(f"of those, the guardian did NOT pass: {len(caught)}/{len(wrong)}")
    if len(caught) < len(wrong):
        print("  The remainder are misses worth reading closely - a wrong heal the guardian passed is")
        print("  the only result here that is genuinely bad news for this product.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analyse", action="store_true", help="read the log and print the tally (free)")
    ap.add_argument("--collector", help="c_* id to probe")
    ap.add_argument("--url", help="the page the collector reads")
    ap.add_argument("--repeat", type=int, default=1, help="repetitions per prompt family")
    ap.add_argument("--prompts", default=None,
                    help=f"comma-separated families (default: all). available: "
                         f"{', '.join(PROMPT_FAMILIES)}")
    args = ap.parse_args(argv)

    if args.analyse:
        analyse(args)
        return
    if not args.collector or not args.url:
        ap.error("--collector and --url are required unless --analyse is given")
    gather(args)


if __name__ == "__main__":
    main()
