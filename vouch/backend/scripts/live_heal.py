"""
Drive one real heal against the live collector, and let the guardian judge it.

This is the end-to-end proof that Vouch's thesis holds against Bright Data rather than against
fixtures: a real `scraper heal` stops at the approval gate, its `preview_result` rows reach the
guardian, and the guardian decides before anything is committed.

    # from vouch/backend
    MOCK_MODE=false python -m scripts.live_heal --prompt-style vague

`--prompt-style vague` sends the deliberately underspecified prompt the demo technique calls for - the
kind a hurried operator writes - which is what makes the heal grab the wrong column. `sharp` sends the
guardian-style precise prompt instead, for comparison.

Nothing is ever committed. Whatever the verdict, the heal is REJECTED at the end, so the collector is
left exactly as it was. Bright Data leaves the scraper unchanged on reject, which is what makes this
safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlmodel import select

from app.config import settings
from app.db import get_session, init_db
from app.guardian.checks import FieldProfile, profile_run, run_all_checks
from app.guardian.verdict import decide
from app.models import Baseline
from app.scraper import baseline as baseline_capture
from app.scraper import brightdata

DOCS = Path(__file__).resolve().parents[2] / "docs"
SAMPLE = DOCS / "sample_output.json"

PROMPTS = {
    # Underspecified on purpose. "Near the delivery info" is the trap: on a Newegg tile the shipping
    # line sits directly under the price, so a healer told to look there is likely to grab it.
    "vague": "the price field looks wrong, re-capture the price near the delivery info",
    # What the guardian itself would ask for.
    "sharp": ("The price field is wrong. Extract each card's own current selling price - the "
              "prominent price the customer pays - not the shipping cost and not any crossed-out "
              "reference price."),
}


def _load_baseline(session, collector_id: str) -> Baseline:
    """The guardian's reference point, rebuilt from the committed sample if it is not in the DB.

    Rebuilding from docs/sample_output.json rather than re-running the collector is deliberate: a run
    costs credits and the sample IS that run, captured at creation time.
    """
    existing = session.exec(
        select(Baseline).where(Baseline.collector_id == collector_id)
    ).first()
    if existing is not None:
        return existing

    if not SAMPLE.exists():
        sys.exit(f"no baseline for {collector_id} and no {SAMPLE.name} to rebuild it from - "
                 f"run scripts.create_collector first")

    rows = brightdata._rows(json.loads(SAMPLE.read_text(encoding="utf-8"))["rows"])
    profiles, count = baseline_capture.capture(rows)
    created = Baseline(collector_id=collector_id, record_count=count, field_profiles=profiles)
    session.add(created)
    session.commit()
    session.refresh(created)
    print(f"  rebuilt baseline from {SAMPLE.name}: {count} rows, "
          f"fields {', '.join(profiles)}")
    return created


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--collector", default=None, help="c_* id (defaults to seed.COLLECTOR_ID)")
    parser.add_argument("--prompt-style", choices=sorted(PROMPTS), default="vague")
    parser.add_argument("--prompt", default=None, help="override the prompt entirely")
    parser.add_argument("--keep", action="store_true",
                        help="do NOT reject at the end (leaves the gate open - almost never what you want)")
    args = parser.parse_args(argv)

    if settings.mock_mode:
        sys.exit("MOCK_MODE is true - this would heal nothing real. Re-run with MOCK_MODE=false.")

    from scripts.seed import COLLECTOR_ID, LIVE_URL

    collector_id = args.collector or COLLECTOR_ID
    prompt = args.prompt or PROMPTS[args.prompt_style]

    init_db()
    print(f"collector : {collector_id}")
    print(f"prompt    : {prompt}")
    print()

    with get_session() as session:
        baseline = _load_baseline(session, collector_id)
        profiles = {k: FieldProfile.from_dict(v) for k, v in baseline.field_profiles.items()}
        baseline_count = baseline.record_count

    print("triggering the heal (this stops at the approval gate, it does not commit) ...")
    proposal = brightdata.propose_heal(collector_id, prompt, LIVE_URL)
    rows = proposal.proposed_records
    print(f"  gate reached: {len(rows)} preview rows")
    if proposal.diff_summary:
        print(f"  diff        : {proposal.diff_summary}")
    if proposal.view_url:
        print(f"  review at   : {proposal.view_url}")

    # What did the heal actually produce?
    proposed_profiles = profile_run(rows)
    print()
    print("  proposed field profile:")
    for name, prof in proposed_profiles.items():
        detail = (f"median={prof.median}" if prof.dtype == "numeric"
                  else f"cardinality={prof.cardinality}" if prof.dtype == "string"
                  else f"true_rate={prof.true_rate}" if prof.dtype == "bool" else "")
        base = profiles.get(name)
        was = (f"  (baseline median={base.median})"
               if base is not None and base.dtype == "numeric" else "")
        print(f"    {name:20} {prof.dtype:8} nulls={prof.null_rate:.0%}  {detail}{was}")

    print()
    print("the guardian judges it BEFORE anything is committed ...")
    verdict = decide(run_all_checks(profiles, rows, baseline_count=baseline_count))
    print(f"  decision   : {verdict.decision.upper()}   confidence {verdict.confidence}/100")
    print(f"  brief      : {verdict.brief}")
    for failure in verdict.failures:
        print(f"    - {failure.severity.value:8} {failure.code:22} {failure.field_name}")

    # Persist the real output for the submission, whichever way it went.
    out = DOCS / f"live_heal_{args.prompt_style}.json"
    out.write_text(json.dumps({
        "_comment": ("A real Scraper Studio heal, captured at the approval gate before any commit, "
                     "with the guardian's verdict on it. Produced by scripts/live_heal.py."),
        "collector_id": collector_id,
        "prompt": prompt,
        "gate_status": "awaiting_approval",
        "diff_summary": proposal.diff_summary,
        "guardian": {
            "decision": verdict.decision,
            "confidence": verdict.confidence,
            "brief": verdict.brief,
            "failures": [{"code": f.code, "severity": f.severity.value,
                          "field": f.field_name, "message": f.message, "evidence": f.evidence}
                         for f in verdict.failures],
        },
        "preview_result": rows,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\n  wrote docs/{out.name}")

    if args.keep:
        print("\n! --keep: the gate is still OPEN. Reject or approve it before running again:")
        print(f"    npx -y @brightdata/cli scraper approve {collector_id} --reject")
        return

    print("\nrejecting, so nothing is committed and the collector is unchanged ...")
    brightdata.reject_heal(collector_id)
    print("  rejected - the previous collector is retained and still operational")


if __name__ == "__main__":
    main()
