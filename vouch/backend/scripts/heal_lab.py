r"""
Run many real heals and record what the healer actually grabbed - varying the PAGE, not the prompt.

The question this exists to answer: does Bright Data's self-heal fail in a PATTERN? You cannot answer
that from the fixtures in this repo. Every wrong heal in tests/fixtures/*.json and in the testbed
generator was written by us in Python, so it reveals what we chose to write and nothing about the
healer. And the three real heals we have on record all extracted the correct field - including the
deliberately vague one - so the honest sample of observed Bright Data failures is currently ZERO.

WHAT CHANGED, AND WHY IT MATTERS
--------------------------------
The first version of this lab varied exactly one axis: the prompt. That axis cannot produce a
finding. An LLM that obeys a badly-worded instruction is behaving correctly; "we told it to grab the
crossed-out price and it grabbed the crossed-out price" is a fact about us, not about Bright Data.
The prompt families are kept because a CONTROL prompt is needed, but they are no longer the
experiment.

The experiment is the PAGE. A trial is now (page, prompt_family): the same sharp, unambiguous prompt
is put to the healer against page structures designed to mislead a code-generating model. If the
healer fails on a prompt that admits one reading, the page did it, and that is a real defect with a
reproducible cause. The comparison is built into `--analyse` rather than left to the eye: a page
effect is only reported when the ADVERSARIAL page failed AND the CLEAN CONTROL page passed on the
same prompt. Control failed too? Then the collector or the prompt is at fault and the page gets no
credit for it.

THE MEASUREMENT PROBLEM THIS FILE EXISTS TO SOLVE
-------------------------------------------------
Hypothesis P1 says a heal can be correct on row 1 and wrong on rows 2-30 - the generated selector
fits the first tile and nothing else. Bright Data's approval gate exposes `preview_result`, and
`preview_result` is ONE ROW (measured; see docs/BRIGHT_DATA_NOTES.md section 2). So a lab that
classifies the preview and always rejects is STRUCTURALLY INCAPABLE of observing P1: a heal that is
right on row 1 and garbage on rows 2-30 scores as a clean pass, and the lab reports "no failures
observed" while sitting on top of one.

`--commit-and-measure` closes that hole. It approves the heal, runs the collector for all ~30 rows,
and measures the full run with the SAME `_measure` used on the preview. Two numbers per trial: what
the one-row gate said, and what the whole page said. The gap between them is the finding. Preview
clean + full run broken is a heal that passes Bright Data's own approval gate while being wrong,
which is the strongest thing this repo could demonstrate, and `--analyse` prints it under a banner
rather than burying it in a tally.

RESETTING BETWEEN TRIALS - AND WHY IT TURNS OUT TO BE CHEAP
-----------------------------------------------------------
Approving looked like it had to mutate the collector, which would make committed trials
non-independent. The three ways out were all bad: (a) a fresh collector per trial - independent, but
`create` is another 5-10 minute AI job, there is NO programmatic delete (BRIGHT_DATA_NOTES section
3) so every trial leaks an orphan, and separately-generated collectors differ in extraction code, so
the page axis gets confounded with collector variance; (b) one committed trial per collector, then
stop - honest but it caps the mode at one data point per collector; (c) heal BACK with the sharp
prompt - cheap, but circular, since the instrument under test is used to repair the instrument, and
on exactly the adversarial pages we care about the repairing heal is the one most likely to fail.

None of the three is needed, because approving does not reach production. From the CLI source
(@brightdata/cli v0.3.5, commands/scraper.js, resume_and_poll):

    const resume_body = approve && opts.autoSave
        ? { message: approve, auto_save: true }
        : { message: approve };

`brightdata.approve_heal()` does not pass `--auto-save`, so `auto_save` is never sent, and Bright
Data's docs describe an accepted change as landing in a DRAFT until an explicit Save to Production.
`scraper run --version dev` runs that draft. So one committed trial is:

    heal -> approve (draft) -> run --version dev (all ~30 rows) -> production untouched

and the next trial starts from the same production template with no repair, no new collector and no
orphan. Cost: one heal plus two runs.

TWO THINGS THAT INFERENCE COULD GET WRONG, BOTH CHECKED RATHER THAN ASSUMED
----------------------------------------------------------------------------
Only the first half of that argument is verified. "The CLI never sends auto_save" is read straight
off the source. "Therefore production is untouched" is INFERRED from the docs, and this harness is
not entitled to spend a run on an inference:

  1. PRODUCTION UNTOUCHED. Every collector's production output is fingerprinted (row count, field
     names, numeric medians) before its first commit, and production is re-run after every approve.
     If the fingerprint moved, approving DID reach production, the whole no-reset argument is void,
     and the run ABORTS immediately with the manual recovery command rather than continuing to
     record trials that are secretly chained.
  2. TRIALS ACTUALLY INDEPENDENT. Even with production untouched, `heal` might refactor the DRAFT
     rather than production, which would silently make trial N+1 a heal of trial N's output. The
     legacy heal payload carries `diff.template_a` - the template the healer started FROM - so this
     is free to check: hash template_a on every trial and compare it to the first one seen for that
     collector. A change after an approve means the trials are a chain, and `--analyse` says so
     instead of reporting a chain as a sample.

THE DIFF IS EVIDENCE, AND IT IS FREE
-------------------------------------
Every heal is asked with `capture_diff=True`, which uses the CLI's `--legacy-output` to get the bare
AI-progress payload instead of the v0.3 envelope. The envelope reduces the diff to "proposed
template has N step(s)"; the raw payload carries the whole {template_a, template_b}. That is the
primary evidence for hypothesis P3 - a healer reasoning over a stale cached DOM - because if the
proposed steps reference class names the live page no longer has, the diff shows it. It needs no
approval, costs no extra call, and is persisted in every record, in both modes.

    # from vouch/backend

    # free, offline, no calls: what would this cost and what would it do?
    python -m scripts.heal_lab --page clean=https://volt.netlify.app/@c_aaa \
                               --page p1=https://volt.netlify.app/p1.html@c_bbb --dry-run

    # the default: real heals, every one REJECTED, collectors unchanged, preview-only measurement
    MOCK_MODE=false python -m scripts.heal_lab \
        --page clean=https://volt.netlify.app/@c_aaa \
        --page p1_first_tile_anomaly=https://volt.netlify.app/p1.html@c_bbb \
        --page p2_label_stripped=https://volt.netlify.app/p2.html@c_ccc \
        --page p3_renamed_dom=https://volt.netlify.app/p3.html@c_ddd \
        --prompts control_sharp --repeat 2

    # the committing mode: approves each heal into the draft and runs it in full
    MOCK_MODE=false python -m scripts.heal_lab --page ... \
        --prompts control_sharp --commit-and-measure yes-approve-heals-and-spend-credits

    # then read the tally, offline and free
    python -m scripts.heal_lab --analyse

By default every attempt is REJECTED, always, so nothing is accepted anywhere and the run is
repeatable. Committing happens only behind `--commit-and-measure <token>`, which prints an estimated
credit cost and what it may change before it touches anything. Deliberately serial: AI-Flow caps
concurrent create/heal at 3 and a 4th returns 429.

Cost note: billing is per page load, and `budget balance` returns 403 for our key, so spend cannot be
polled - the harness counts runs and heals itself and prints a running estimate. A run is one page
load; a heal's cost is undocumented and is budgeted pessimistically at two. On the single-page
testbed a load is 1 credit; on the 96-tile Newegg category page it is ~97, so pass `--page-cost 97`
there and expect the estimate to hurt. Probe the cheap page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
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

# Bumped when the record shape changes. Records without it are schema 1 (prompt axis, preview only)
# and `analyse` reads them through `_norm` rather than crashing on the fields they do not have.
SCHEMA = 2

# Typing this exactly is the confirmation. A bare --commit flag is one fat finger away from spending
# credits and accepting a heal; a token that has to be copied is not.
CONFIRM_TOKEN = "yes-approve-heals-and-spend-credits"

# Prompt families, each probing a different way an operator can be unclear. They are retained as
# instruments, not as the experiment: `control_sharp` is the one the page axis is run against, and
# the others exist so a page finding can be checked for prompt-sensitivity.
#
# `misleading_*` were the load-bearing pair of the old set. They are not ambiguous at all - they are
# clear and WRONG. If the healer obeys them, that tells us the healer trusts the prompt over the
# page, which is more useful than "vague prompts are risky": it means a confident operator can break
# a scraper in a way no amount of prompt hygiene would catch.
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

# Checks a one-row preview CANNOT emit, because run_all_checks stands them down for samples
# (ROW_COUNT_SHIFT, CARDINALITY_COLLAPSE) or because one row carries no distribution (NUMERIC_DRIFT).
#
# This matters for honesty about the preview/full gap. If the full run fails only on these, the two
# measurements did not have the same checks available, so part of the gap is an artefact of our own
# instrument. It is still a real gate blind spot - the gate structurally cannot show you a row count
# - but it is NOT evidence for P1, which is a claim about the price column being right on row 1 and
# wrong after it. `_blind_spot_kind` separates the two and `analyse` reports them apart.
SAMPLE_BLIND_CODES = frozenset({"ROW_COUNT_SHIFT", "CARDINALITY_COLLAPSE", "NUMERIC_DRIFT"})

# The draft version name `scraper run --version <v>` is given to read an approved-but-unsaved heal.
DRAFT_VERSION = "dev"

# Cost model, in PAGE LOADS - Bright Data bills per load, and `budget balance` 403s for our key, so
# the meter here is arithmetic rather than measurement. A `run` is one load. A heal's cost is
# undocumented; it is budgeted at two because it must at minimum fetch the page to regenerate the
# template and again to build the preview. Runs are counted exactly; heals are an upper-bound guess.
LOADS_PER_RUN = 1
LOADS_PER_HEAL = 2
MINUTES_PER_HEAL = 7          # the CLI's own docs say 5-10
DEFAULT_MAX_CREDITS = 1000    # refuse to start, and abort mid-run, past this arithmetic estimate

# A template diff is unbounded in size and this log is meant to stay greppable. Past this, the
# templates are replaced by their hashes and step counts, which is what the analysis reads anyway.
MAX_DIFF_CHARS = 200_000


class DraftAssumptionError(RuntimeError):
    """Approving reached PRODUCTION, so the committing mode's safety argument is void.

    Raised when a collector's production fingerprint moves after an approve. Everything about the
    no-reset protocol depends on production being untouched; once that is false, the collector is
    changed, the next trial would heal a changed template, and continuing would produce a chain
    labelled as a sample. Aborting and saying so is the only honest response.
    """


@dataclass
class Page:
    """One page under test, the collector that reads it, and whether it is the clean control."""
    name: str
    url: str
    collector: str
    is_control: bool = False


@dataclass
class Meter:
    """Runs and heals performed, and what they are estimated to have cost.

    Spend cannot be polled - `budget balance` returns 403 for this key - so the only honest budget
    control is to count the calls we make ourselves and multiply. Runs are exact (one page load
    each). Heals are a guess, flagged as one everywhere it is printed.
    """
    page_cost: int = 1
    runs: int = 0
    heals: int = 0

    @property
    def loads(self) -> int:
        return self.runs * LOADS_PER_RUN + self.heals * LOADS_PER_HEAL

    @property
    def credits(self) -> int:
        return self.loads * self.page_cost

    def line(self) -> str:
        return (f"spent so far (estimated): {self.runs} runs + {self.heals} heals "
                f"= ~{self.credits} credits")


def parse_page_spec(spec: str) -> Page:
    """Parse `NAME=URL@COLLECTOR` into a Page.

    Split on the FIRST '=' and the LAST '@': URLs carry '=' in query strings and could in principle
    carry '@' in userinfo, so the greedy choice in each direction is the safe one.
    """
    if "=" not in spec:
        raise ValueError(f"page spec {spec!r} has no '=' - expected NAME=URL@COLLECTOR")
    name, rest = spec.split("=", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"page spec {spec!r} has an empty name")
    if "@" not in rest:
        raise ValueError(f"page spec {spec!r} names no collector - expected NAME=URL@COLLECTOR")
    url, collector = rest.rsplit("@", 1)
    url, collector = url.strip(), collector.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"page spec {spec!r} has no http(s) url (got {url!r})")
    if not collector:
        raise ValueError(f"page spec {spec!r} has an empty collector id")
    return Page(name=name, url=url, collector=collector)


def pages_from_args(args) -> list[Page]:
    """Build the page axis from --page, or from the single-page --collector/--url shorthand.

    The shorthand is never marked as the control. Silently promoting one unnamed page to "the clean
    baseline everything is compared against" would let a run pointed at a BROKEN page license a page
    finding, which is precisely the error the control exists to prevent.
    """
    if args.page:
        pages = [parse_page_spec(spec) for spec in args.page]
        names = [p.name for p in pages]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate page names: {', '.join(sorted(dupes))}")
        control = args.control or ("clean" if "clean" in names else None)
        if control is not None:
            if control not in names:
                raise ValueError(f"--control {control!r} is not one of the pages: {', '.join(names)}")
            for p in pages:
                p.is_control = p.name == control
        return pages
    return [Page(name=args.page_name, url=args.url, collector=args.collector, is_control=False)]


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


# --------------------------------------------------------------------------------------
# One measurement, used for BOTH the preview and the full run
# --------------------------------------------------------------------------------------

def _measure(rows: list[dict], baseline: dict[str, FieldProfile], baseline_count: int,
             *, is_sample: bool, field: str = "price") -> dict:
    """Judge one set of rows: the guardian's verdict, plus what the price column actually is.

    The whole committing mode rests on the preview number and the full-run number being COMPARABLE,
    so both go through this one function. Two code paths computing "was this heal correct" two ways
    would make the gap between them a measurement of our own inconsistency instead of a measurement
    of the healer.

    `is_sample` is passed through to run_all_checks rather than decided here: the preview IS a sample
    (volume checks stand down), the full run is not (they apply). That asymmetry is real and it is
    exactly why the gap has to be read with SAMPLE_BLIND_CODES in hand.
    """
    verdict = decide(run_all_checks(baseline, rows, baseline_count, is_sample=is_sample))
    grabbed = _classify(rows, baseline, field)
    measured = {
        "rows": len(rows),
        "is_sample": is_sample,
        "price_looks_like": grabbed["looks_like"],
        "price_median": grabbed["median"],
        "nearest": grabbed["nearest"],
        "distances": grabbed["distances"],
        "decision": verdict.decision,
        "confidence": verdict.confidence,
        "codes": sorted({f.code for f in verdict.failures}),
        # Which failures name the price column itself. Kept separately because "the heal broke the
        # price" and "the heal broke something else" are different findings, and the whole
        # preview/full comparison turns on telling them apart.
        "price_codes": sorted({f.code for f in verdict.failures if f.field_name == field}),
        "first_row": rows[0] if rows else None,
    }
    measured["clean"] = _clean(measured)
    return measured


def _clean(m: dict | None) -> bool:
    """Did the guardian find no reason to refuse this? AND no other field is named.

    Note what is NOT required: that the classifier positively says "price". That test is wrong at
    n=1, and n=1 is exactly what the gate hands us. On a single row `_profile_distance` compares two
    medians and nothing else, so one expensive tile - the $1,999 flagship against a $565 catalogue
    median - sits 2.5 away from its own baseline field and gets no label at all. Demanding a positive
    "price" would score that perfectly correct heal as dirty, and every blind-spot comparison built
    on top of it would be measuring the sample size instead of the healer.

    `looks_like is None` means "nothing explains these values" - a refusal to claim, not a finding.
    Treat it as no evidence and let the verdict decide. A label that positively names some OTHER
    field is evidence, and it overrides a passing verdict: claiming a label at all requires the
    values to sit within MAX_LABEL_DISTANCE of that field's distribution, which is a much stronger
    statement than "nearest".

    WHY A SAMPLE IS TESTED DIFFERENTLY FROM A FULL RUN.
    The guardian now refuses to reach PASS on partial evidence at all - a preview can reject but
    never confirm, because a clean result from two non-random rows is not a confirmation (see
    app/guardian/checks.py, Evidence). A preview's best possible verdict is therefore REVIEW, so
    `decision == "pass"` would score EVERY preview dirty and this lab would report zero blind spots
    forever - measuring the guardian's new caution instead of the healer's behaviour.

    The question this predicate asks has to match what the lab is measuring, which is what the GATE
    showed, not what the guardian was willing to promise on the strength of it. For a preview that
    is "did anything come back wrong?" - no findings at all. For a full run the guardian has seen
    everything, so its own PASS is the right and stricter test. The distinction is the same one the
    guardian draws; it is not a loophole opened here.
    """
    if not m:
        return False
    if m.get("price_looks_like") not in (None, "price"):
        return False
    if m.get("is_sample"):
        return not m.get("codes")
    return m.get("decision") == "pass"


def _label(m: dict | None) -> str:
    """How a label reads in a report. None is 'unclassifiable', which is a result, not a null."""
    return (m or {}).get("price_looks_like") or "unclassifiable"


def _blind_spot_kind(preview: dict | None, full: dict | None) -> str | None:
    """Did the one-row gate say yes to something the whole page says no to, and of which kind?

    Returns None when there is no gap to report, otherwise:

      "row1_overfit"  the PRICE COLUMN is implicated on the full run - it sits on another field's
                      distribution, or a check named `price` failed. Evidence FOR P1: right on row 1,
                      wrong after it.
      "volume_only"   the price column is intact and the only failures are ones a one-row preview
                      structurally cannot emit (a row count, a collapsed cardinality). A genuine
                      blind spot in Bright Data's gate, which cannot show you a row count, but not
                      evidence that the extraction overfit to the first tile.
      "other_field"   the price column is intact and some OTHER field broke in a way the sampled row
                      happened not to show. Also a real miss by the gate, also not P1.

    The separating question is which FIELD the failures name, not which codes fired, and the answer
    comes from the guardian's own `field_name` rather than from a second opinion computed here.
    Going by codes alone gets the flagship case backwards: a heal that reads the shipping line on
    rows 2-30 drags the price median from $565 to $15 and reports only NUMERIC_DRIFT, which is on the
    list of codes a preview cannot emit - so a code-based rule would file the strongest P1 result
    under "volume artefact".
    """
    if not preview or not full:
        return None
    if not _clean(preview) or _clean(full):
        return None
    if full.get("price_looks_like") not in (None, "price") or full.get("price_codes"):
        return "row1_overfit"
    codes = set(full.get("codes") or [])
    return "volume_only" if codes <= SAMPLE_BLIND_CODES else "other_field"


# --------------------------------------------------------------------------------------
# Evidence: what the collector returns, and what the healer proposed to change
# --------------------------------------------------------------------------------------

def _fingerprint(rows: list[dict]) -> dict:
    """A coarse, stable summary of a run, for "has this collector changed?" comparisons.

    Coarse on purpose. It has to be identical across two runs of an UNCHANGED collector against a
    static page, so it must exclude anything that legitimately varies - row order, string payloads,
    a tile that re-rendered. Row count, field names and numeric medians satisfy that while still
    moving decisively if the extraction starts reading a different column.
    """
    prof = profile_run(rows)
    return {
        "rows": len(rows),
        "fields": sorted(prof),
        "medians": {n: p.median for n, p in sorted(prof.items())
                    if p.dtype == "numeric" and p.median is not None},
    }


def _template_hash(template: object) -> str | None:
    """Short stable hash of a template, so lineage can be compared without storing it twice."""
    if not isinstance(template, dict):
        return None
    blob = json.dumps(template, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _diff_facts(raw_diff: dict | None) -> dict:
    """Pull the machine-readable parts out of the heal's raw {template_a, template_b} diff.

    `template_a` is what the healer started FROM, which is how trial independence gets checked, and
    `template_b` is what it proposes - the only place the generated selectors are visible without
    approving anything. Both are kept whole unless the pair is enormous, in which case the hashes and
    step counts survive and the bodies do not; those are what the analysis actually reads.
    """
    if not isinstance(raw_diff, dict):
        return {"template_a_hash": None, "template_b_hash": None, "diff": None}
    a, b = raw_diff.get("template_a"), raw_diff.get("template_b")
    facts = {
        "template_a_hash": _template_hash(a),
        "template_b_hash": _template_hash(b),
        "template_a_steps": len(a["steps"]) if isinstance(a, dict) and isinstance(a.get("steps"), list) else None,
        "template_b_steps": len(b["steps"]) if isinstance(b, dict) and isinstance(b.get("steps"), list) else None,
    }
    blob = json.dumps(raw_diff, default=str)
    facts["diff"] = (raw_diff if len(blob) <= MAX_DIFF_CHARS
                     else {"truncated": True, "chars": len(blob)})
    return facts


# --------------------------------------------------------------------------------------
# Planning and cost
# --------------------------------------------------------------------------------------

def _plan(pages: list[Page], families: list[str], repeat: int, committing: bool,
          page_cost: int) -> dict:
    """What this run will do and what it will cost, computed before anything is called."""
    trials = len(pages) * len(families) * repeat
    heals = trials
    runs = 1                                   # the one baseline capture
    if committing:
        runs += len(pages) - 1                 # a production fingerprint per other collector
        runs += trials * 2                     # the draft run, and the production re-check
    loads = runs * LOADS_PER_RUN + heals * LOADS_PER_HEAL
    return {"trials": trials, "heals": heals, "runs": runs,
            "minutes": heals * MINUTES_PER_HEAL,
            "page_loads": loads, "credits": loads * page_cost}


def _print_plan(pages: list[Page], families: list[str], args, plan: dict, committing: bool) -> None:
    print("pages")
    for p in pages:
        tag = "   (CONTROL)" if p.is_control else ""
        print(f"  {p.name:28} {p.url}  [{p.collector}]{tag}")
    print(f"families  : {', '.join(families)}")
    print(f"repeat    : {args.repeat}")
    print(f"mode      : {'COMMIT to draft + FULL RUN' if committing else 'reject-only (nothing accepted)'}")
    print(f"trials    : {plan['trials']}   heals: {plan['heals']}   runs: {plan['runs']}")
    print(f"est. time : {plan['minutes']} min ({MINUTES_PER_HEAL} min/heal, serial by design)")
    print(f"est. cost : ~{plan['credits']} credits "
          f"({plan['page_loads']} page loads x {args.page_cost}/load; runs exact, heals a guess)")
    print(f"budget cap: {args.max_credits} credits")
    print(f"log       : {LOG}")
    if not any(p.is_control for p in pages):
        print("note      : no control page - --analyse cannot attribute any failure to page structure")
    print()


def _print_commit_warning(pages: list[Page], plan: dict) -> None:
    ids = sorted({p.collector for p in pages})
    bar = "#" * 78
    print(bar)
    print("#  COMMIT MODE - this APPROVES each heal against a real collector.")
    print("#")
    print("#  Approving without --auto-save is expected to land the template in the DRAFT version,")
    print("#  leaving production untouched. That is INFERRED from the docs, not verified, so this")
    print("#  run checks it: production is fingerprinted first and re-run after every approve, and")
    print("#  the run ABORTS the moment the fingerprint moves. If it does, the collector has been")
    print("#  changed for real and there is no programmatic delete - you would repair it by hand at")
    print("#  https://brightdata.com/cp/scrapers .")
    print("#")
    print(f"#  collectors touched : {', '.join(ids)}")
    print(f"#  estimated cost     : ~{plan['credits']} credits, ~{plan['minutes']} min")
    print("#")
    print("#  Ctrl-C now if that is not what you want.")
    print(bar)
    print()


# --------------------------------------------------------------------------------------
# Gather
# --------------------------------------------------------------------------------------

def _append(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def _reject(collector: str, record: dict) -> None:
    """Answer the gate with NO, whatever happened, so the collector is never left waiting."""
    try:
        brightdata.reject_heal(collector)
        record["rejected"] = True
    except Exception as exc:  # noqa: BLE001
        record["rejected"] = False
        record["reject_error"] = f"{type(exc).__name__}: {exc}"
        print(f"  !! could not reject: {record['reject_error']}")
        print("     answer the gate by hand before running again:")
        print(f"     npx -y @brightdata/cli scraper approve {collector} --reject")


def _legacy_aliases(record: dict, preview: dict) -> None:
    """Mirror the preview measurement onto the schema-1 key names.

    One log file, two readers. The records already sitting in this file were written flat, and
    anything else that learned to read them keeps working if new records carry the same keys. The
    nested `preview`/`full` objects are the source of truth; these are copies of the preview half.
    """
    record.update({
        "preview_rows": preview["rows"],
        "extracted": preview["first_row"],
        "price_looks_like": preview["price_looks_like"],
        "price_median": preview["price_median"],
        "distances": preview["distances"],
        "decision": preview["decision"],
        "confidence": preview["confidence"],
        "codes": preview["codes"],
    })


def _commit_and_measure(page: Page, record: dict, baseline: dict[str, FieldProfile],
                        baseline_count: int, meter: Meter, production: dict[str, dict]) -> None:
    """Approve into the draft, run the draft in full, and prove production did not move.

    The order matters. The draft run has to happen before the production check, because the check is
    what licenses the NEXT trial - and if it fails, this trial's measurement is still worth keeping
    even though everything after it is void.
    """
    collector = page.collector
    try:
        brightdata.approve_heal(collector)      # no --auto-save: draft, not production
        record["committed"] = True
        record["rejected"] = False
    except Exception as exc:  # noqa: BLE001
        record["committed"] = False
        record["approve_error"] = f"{type(exc).__name__}: {exc}"
        print(f"  !! could not approve: {record['approve_error']}")
        _reject(collector, record)
        return

    try:
        rows = brightdata.run(collector, page.url, version=DRAFT_VERSION)
        meter.runs += 1
    except Exception as exc:  # noqa: BLE001
        record["full_error"] = f"{type(exc).__name__}: {exc}"
        print(f"  !! approved but the draft run failed: {record['full_error']}")
        print(f"     (a heal is accepted into {DRAFT_VERSION} for {collector} and was never measured)")
        return

    full = _measure(rows, baseline, baseline_count, is_sample=False)
    record["full"] = full
    record["full_version"] = DRAFT_VERSION
    record["blind_spot"] = _blind_spot_kind(record.get("preview"), full)
    print(f"  -> FULL RUN ({DRAFT_VERSION}): {full['rows']} rows · {full['decision'].upper()} "
          f"{full['confidence']}/100 · price looks like {_label(full)} "
          f"(median {full['price_median']})")
    if record["blind_spot"] == "row1_overfit":
        print("     *** GATE BLIND SPOT: the one-row preview was clean and the full run is NOT ***")
    elif record["blind_spot"] == "volume_only":
        print("     (blind spot, volume-only: the preview could not have emitted these codes)")
    elif record["blind_spot"] == "other_field":
        print("     (blind spot, another field: the price column is intact, the break is elsewhere)")

    # The check that licenses the next trial: did approving leak into production?
    before = production.get(collector)
    after_rows = brightdata.run(collector, page.url)
    meter.runs += 1
    after = _fingerprint(after_rows)
    record["production_fingerprint"] = after
    record["production_unchanged"] = (before == after)

    # The other half of the same inference, and the one that fails SILENTLY. "Production did not
    # move" is equally true if `--version dev` never addressed the draft and the run we just called
    # "the full measurement" was production all along. Then every committed trial measures the
    # unhealed collector, every gap reads as zero, and the mode looks like it worked. There is no
    # extra call needed to notice: if the heal proposed a real change and the draft run is
    # indistinguishable from production, that is the shape of a no-op flag. One trial proves
    # nothing - a good heal can leave the output identical - so it is recorded per trial and only
    # judged in aggregate by `analyse`.
    record["draft_matches_production"] = (_fingerprint(rows) == after)
    record["heal_proposed_a_change"] = (
        None if not record.get("template_a_hash") or not record.get("template_b_hash")
        else record["template_a_hash"] != record["template_b_hash"])
    if before != after:
        record["quarantined"] = True
        raise DraftAssumptionError(
            f"approving changed PRODUCTION on {collector}.\n"
            f"  before: {json.dumps(before, default=str)}\n"
            f"  after : {json.dumps(after, default=str)}\n"
            f"The no-reset protocol assumed an approve without --auto-save stays in the draft. It "
            f"does not, so this collector is now serving the healed template and every later trial "
            f"would have been a heal of a heal. Repair it by hand (heal with the sharp prompt and "
            f"approve, or rebuild it) at https://brightdata.com/cp/scrapers ."
        )
    print("     production unchanged after approve - the draft assumption holds")


def gather(args) -> None:
    try:
        pages = pages_from_args(args)
    except ValueError as exc:
        sys.exit(str(exc))

    families = (args.prompts.split(",") if args.prompts else list(PROMPT_FAMILIES))
    unknown = [f for f in families if f not in PROMPT_FAMILIES]
    if unknown:
        sys.exit(f"unknown prompt families: {', '.join(unknown)}\n"
                 f"available: {', '.join(PROMPT_FAMILIES)}")

    committing = args.commit_and_measure is not None
    if committing and args.commit_and_measure != CONFIRM_TOKEN:
        sys.exit(f"--commit-and-measure needs the exact token {CONFIRM_TOKEN!r}.\n"
                 f"It approves heals against real collectors and spends credits.")

    plan = _plan(pages, families, args.repeat, committing, args.page_cost)
    _print_plan(pages, families, args, plan, committing)
    if plan["credits"] > args.max_credits:
        sys.exit(f"estimated {plan['credits']} credits exceeds --max-credits {args.max_credits}. "
                 f"Cut --repeat or --prompts, or raise the cap deliberately.")

    # --dry-run makes no external call at all, so it is free and safe in any mode. It exists so the
    # credit estimate can be read BEFORE the money is spent, which is the only time it is useful.
    if args.dry_run:
        print("--dry-run: nothing was called. Drop the flag to run it for real.")
        return

    if settings.mock_mode:
        sys.exit("MOCK_MODE is true - this would heal nothing real. Re-run with MOCK_MODE=false.")

    if committing:
        _print_commit_warning(pages, plan)

    meter = Meter(page_cost=args.page_cost)

    # ONE baseline, captured from the control page, used to judge every trial on every page.
    #
    # This is deliberate and it is half the point of having a control. The baseline is a statement
    # about the STOREFRONT - price ~$565, shipping ~$15, rating ~4.2 - not about any one collector,
    # and the adversarial pages sell the same catalogue through a different DOM. Re-capturing a
    # baseline from each adversarial page would measure that page with a ruler cut from itself: a
    # collector already misreading it would define its own misreading as correct, and the cross-page
    # comparison would compare nothing.
    reference = next((p for p in pages if p.is_control), pages[0])
    print(f"capturing the baseline from '{reference.name}' ({reference.collector}) ...")
    base_rows = brightdata.run(reference.collector, reference.url)
    meter.runs += 1
    baseline = profile_run(base_rows)
    print(f"  {len(base_rows)} rows, numeric fields: "
          f"{', '.join(n for n, p in baseline.items() if p.dtype == 'numeric')}")
    for name, p in baseline.items():
        if p.dtype == "numeric":
            print(f"    {name:16} median {p.median}")

    # Production fingerprints, so "did the approve leak?" has something to compare against. The
    # reference page's own baseline run IS its fingerprint, so only the other collectors cost a run.
    production: dict[str, dict] = {}
    if committing:
        production[reference.collector] = _fingerprint(base_rows)
        for page in pages:
            if page.collector in production:
                continue
            print(f"fingerprinting production for {page.collector} ({page.name}) ...")
            production[page.collector] = _fingerprint(brightdata.run(page.collector, page.url))
            meter.runs += 1
    print()

    # template_a of the FIRST heal seen on each collector. Every later heal on that collector should
    # report the same template_a; if it does not, the healer is refactoring something we changed, and
    # the trials are a chain rather than independent samples.
    first_template: dict[str, str] = {}
    aborted = None
    done = 0

    for rep in range(args.repeat):
        for page in pages:
            for family in families:
                prompt = PROMPT_FAMILIES[family]
                done += 1
                collector = page.collector
                label = f"[{done}/{plan['trials']}] {page.name}/{family} rep{rep + 1}"
                print(f"{label}: healing {collector} ...", flush=True)

                record = {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "schema": SCHEMA,
                    "kind": "trial",
                    "page": page.name,
                    "is_control_page": page.is_control,
                    "collector_id": collector,
                    "url": page.url,
                    "family": family,
                    "repetition": rep + 1,
                    "prompt": prompt,
                    "mode": "commit" if committing else "reject",
                    "baseline_page": reference.name,
                    "baseline_rows": len(base_rows),
                    "committed": False,
                }
                started = time.monotonic()
                try:
                    proposal = brightdata.propose_heal(collector, prompt, page.url,
                                                       capture_diff=True)
                    meter.heals += 1
                    preview = _measure(proposal.proposed_records, baseline, len(base_rows),
                                       is_sample=proposal.is_sample)
                    record["ok"] = True
                    record["seconds"] = round(time.monotonic() - started, 1)
                    record["preview"] = preview
                    record["gate_status"] = proposal.gate_status
                    record["diff_summary"] = proposal.diff_summary
                    record.update(_diff_facts(proposal.raw_diff))
                    _legacy_aliases(record, preview)

                    # Independence check, free, from the diff we already have. A missing hash is
                    # recorded as "unknown" and must NOT seed the comparison - otherwise one heal
                    # that came back without a diff would make every later heal look like a chain.
                    started_hash = record["template_a_hash"]
                    if started_hash is None:
                        record["started_from_first_template"] = None
                    else:
                        seen = first_template.setdefault(collector, started_hash)
                        record["started_from_first_template"] = (started_hash == seen)
                    if record["started_from_first_template"] is False:
                        print("     !! this heal started from a DIFFERENT template than the first "
                              "heal on this collector -")
                        print("        the trials are a chain, not independent samples. Recorded.")

                    print(f"  -> PREVIEW ({preview['rows']} row): "
                          f"{preview['decision'].upper()} {preview['confidence']}/100 · "
                          f"price looks like {_label(preview)} "
                          f"(median {preview['price_median']}) · {record['seconds']}s")
                except Exception as exc:  # noqa: BLE001 - one bad heal must not end the run
                    record.update({"ok": False, "seconds": round(time.monotonic() - started, 1),
                                   "error": f"{type(exc).__name__}: {exc}"})
                    print(f"  -> FAILED: {record['error']}")

                # Answer the gate. Rejecting is the default and the only path that accepts nothing
                # anywhere; approving happens solely in committing mode, and only when there is a
                # measured preview for the full run to be compared against.
                try:
                    if committing and record.get("ok"):
                        _commit_and_measure(page, record, baseline, len(base_rows), meter,
                                            production)
                    else:
                        _reject(collector, record)
                except DraftAssumptionError as exc:
                    record["draft_assumption_failed"] = str(exc)
                    aborted = exc
                finally:
                    _append(record)

                if aborted is not None:
                    break
                print(f"     {meter.line()}")
                if meter.credits > args.max_credits:
                    aborted = RuntimeError(
                        f"budget cap reached: ~{meter.credits} credits estimated, cap is "
                        f"{args.max_credits}. Stopping with {done}/{plan['trials']} trials done.")
                    break
            if aborted is not None:
                break
        if aborted is not None:
            break

    print(f"\nwrote {done} attempts to {LOG.name}")
    print(meter.line())
    if aborted is not None:
        print()
        print("#" * 78)
        print("#  RUN ABORTED")
        print("#" * 78)
        print(str(aborted))
        print()
    print("now: python -m scripts.heal_lab --analyse")


# --------------------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------------------

def _norm(rec: dict) -> dict:
    """Read a record of any schema version into the one shape `analyse` reasons about.

    Schema 1 had no page axis and only ever measured the preview, at the top level of the record.
    Rather than special-case that in five places it is lifted into the nested shape here - and its
    page becomes "(unlabelled)", never the control, so old records can sit in the same log without
    silently supplying a control that was never captured as one.
    """
    preview = rec.get("preview")
    if preview is None and rec.get("ok"):
        preview = {
            "rows": rec.get("preview_rows"),
            "is_sample": True,
            "price_looks_like": rec.get("price_looks_like"),
            "price_median": rec.get("price_median"),
            "distances": rec.get("distances") or {},
            "decision": rec.get("decision"),
            "confidence": rec.get("confidence"),
            "codes": rec.get("codes") or [],
            "first_row": rec.get("extracted"),
        }
        preview["clean"] = _clean(preview)
    full = rec.get("full")
    return {
        "kind": rec.get("kind", "trial"),
        "page": rec.get("page") or "(unlabelled)",
        "is_control": bool(rec.get("is_control_page")),
        "family": rec.get("family") or "?",
        "collector_id": rec.get("collector_id"),
        "ok": bool(rec.get("ok")),
        "committed": bool(rec.get("committed")),
        "preview": preview,
        "full": full,
        "blind_spot": rec.get("blind_spot") or _blind_spot_kind(preview, full),
        "raw": rec,
    }


def _best(t: dict) -> tuple[dict | None, str]:
    """The measurement to judge a trial by, and which one it is.

    The full run whenever there is one: it is the whole page rather than one row of it. Falling back
    to the preview is not equivalent and is marked as such wherever it is used, because a conclusion
    drawn from a one-row sample is a weaker claim than the same conclusion drawn from thirty.
    """
    if t.get("full"):
        return t["full"], "full"
    return t.get("preview"), "preview"


def _cell(trials: list[dict]) -> dict:
    """Collapse the trials in one (page, family) cell to the numbers the comparison needs."""
    clean = sum(1 for t in trials if _clean(_best(t)[0]))
    basis = "full" if trials and all(_best(t)[1] == "full" for t in trials) else "preview"
    return {"n": len(trials), "clean": clean, "basis": basis}


def analyse(_args) -> None:
    if not LOG.exists():
        sys.exit(f"no {LOG.name} yet - run the gather mode first")

    records = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    normalised = [_norm(r) for r in records]
    trials = [t for t in normalised if t["kind"] == "trial" and t["ok"]]
    print(f"records logged   : {len(records)}  ({len(trials)} usable trials, "
          f"{len(records) - len(trials)} errored/skipped)")
    if not trials:
        return

    ids = sorted({t["collector_id"] for t in trials if t["collector_id"]})
    print(f"collectors       : {', '.join(ids)}")
    print(f"pages            : {', '.join(sorted({t['page'] for t in trials}))}")
    measured_full = [t for t in trials if t["full"]]
    print(f"full-run measured: {len(measured_full)}/{len(trials)} trials "
          f"({len(trials) - len(measured_full)} judged on a ONE-ROW preview only)")
    print()

    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in trials:
        by_cell[(t["page"], t["family"])].append(t)
    pages = sorted({t["page"] for t in trials})
    families = sorted({t["family"] for t in trials})

    # The headline: per page and prompt, what did the healer actually grab?
    print("what the healer put in `price`, by page and prompt")
    print(f"  {'page':24} {'family':20} {'n':>3}  {'grabbed':<28} decisions")
    for page in pages:
        for family in families:
            rs = by_cell.get((page, family))
            if not rs:
                continue
            grabbed = Counter((_best(r)[0] or {}).get("price_looks_like") or "?" for r in rs)
            decisions = Counter((_best(r)[0] or {}).get("decision") or "?" for r in rs)
            g = ", ".join(f"{k}x{v}" for k, v in grabbed.most_common())
            d = ", ".join(f"{k}x{v}" for k, v in decisions.most_common())
            print(f"  {page:24} {family:20} {len(rs):>3}  {g:<28} {d}")

    _print_page_findings(trials, by_cell, pages, families)
    _print_blind_spots(trials)
    _print_integrity(normalised, trials)

    # Is the healer deterministic? Same prompt, same page, same answer?
    print()
    print("determinism: distinct price medians returned per page and prompt")
    for (page, family), rs in sorted(by_cell.items()):
        medians = {(_best(r)[0] or {}).get("price_median") for r in rs}
        verdict = "deterministic" if len(medians) == 1 else f"{len(medians)} distinct outcomes"
        print(f"  {page:24} {family:20} {len(rs):>3} run(s) -> {verdict}  "
              f"{sorted(m for m in medians if m is not None)}")

    # Did anything actually go wrong? This is the number the question hangs on.
    wrong = [t for t in trials
             if (_best(t)[0] or {}).get("price_looks_like") not in (None, "price")]
    print()
    print(f"heals that grabbed a field other than `price`: {len(wrong)} of {len(trials)}")
    if not wrong:
        print("  No observed Bright Data mis-heal in this sample. A pattern cannot be reported from")
        print("  zero events - say so plainly rather than reaching for the synthetic fixtures, which")
        print("  only show what we wrote.")
    for t in wrong:
        m, basis = _best(t)
        print(f"  {t['page']:24} {t['family']:20} grabbed '{m['price_looks_like']}' "
              f"(median {m['price_median']}) · {str(m['decision']).upper()} {m['confidence']}/100 "
              f"· codes {','.join(m['codes']) or 'none'} · from the {basis}")

    if wrong:
        caught = [t for t in wrong if (_best(t)[0] or {}).get("decision") != "pass"]
        print()
        print(f"of those, the guardian did NOT pass: {len(caught)}/{len(wrong)}")
        if len(caught) < len(wrong):
            print("  The remainder are misses worth reading closely - a wrong heal the guardian")
            print("  passed is the only result here that is genuinely bad news for this product.")


def _print_page_findings(trials: list[dict], by_cell: dict, pages: list[str],
                         families: list[str]) -> None:
    """Attribute failures to page STRUCTURE, which requires the control to have passed.

    This is the comparison the lab exists to make, computed rather than eyeballed. An adversarial
    page failing proves nothing on its own - the collector might be bad, the prompt might be bad, the
    healer might be having a bad day. It becomes a page finding only when the SAME prompt against the
    clean control page came back clean. If the control failed too, the page is not what did it, and
    saying so is the whole reason the control is in the run.
    """
    control_pages = sorted({t["page"] for t in trials if t["is_control"]})
    print()
    print("page findings: does this page break the healer on a prompt the clean page survives?")
    if not control_pages:
        print("  NO CONTROL PAGE in this log. Nothing here can be attributed to page structure -")
        print("  re-run with --page clean=<url>@<collector> --control clean.")
        return

    control_cells: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        if t["is_control"]:
            control_cells[t["family"]].append(t)

    print(f"  control page(s): {', '.join(control_pages)}")
    print(f"  {'page':24} {'family':20} {'control':>9} {'this page':>10}  verdict")
    any_row = False
    for page in pages:
        if page in control_pages:
            continue
        for family in families:
            adv = by_cell.get((page, family))
            if not adv:
                continue
            any_row = True
            ctl = control_cells.get(family, [])
            a, c = _cell(adv), _cell(ctl)
            if not ctl:
                verdict = "no control for this prompt - not attributable"
            elif c["clean"] < c["n"]:
                verdict = "control failed too - blame the collector or the prompt, not the page"
            elif a["clean"] == 0:
                verdict = "*** PAGE DEFECT: control clean, this page never clean ***"
            elif a["clean"] < a["n"]:
                verdict = f"INTERMITTENT on this page ({a['n'] - a['clean']}/{a['n']} failed)"
            else:
                verdict = "page survived"
            weak = "" if a["basis"] == "full" and c["basis"] == "full" else "   [preview-only]"
            print(f"  {page:24} {family:20} {c['clean']:>4}/{c['n']:<4} {a['clean']:>5}/{a['n']:<4}"
                  f"  {verdict}{weak}")
    if not any_row:
        print("  only control-page trials in this log - nothing to compare against.")
    print("  [preview-only] means the cell was judged on one row, which cannot see a row-1 overfit;")
    print("  such a cell can call a page clean when it is not. Re-run it with --commit-and-measure.")


def _print_blind_spots(trials: list[dict]) -> None:
    """Heals that passed Bright Data's own gate and were still wrong. The first-class finding.

    A heal whose one-row preview is clean and whose full run is not is a heal that a human at the
    Scraper Studio approval screen would have accepted - the screen shows the diff, the CLI shows
    that one row, and both of them looked fine. Nothing downstream would have caught it either,
    because the template is accepted by then and simply returns wrong numbers from that point on.
    This is the strongest evidence this repo can produce that a pre-commit DATA check is worth
    having, so it gets a banner rather than a table row.
    """
    measured = [t for t in trials if t["full"]]
    print()
    if not measured:
        print("gate blind spot: UNMEASURED. Every trial here was judged on the one-row preview, and")
        print("  a one-row preview cannot tell a correct heal from one that is correct on row 1 only.")
        print(f"  To measure it: --commit-and-measure {CONFIRM_TOKEN}")
        return

    overfit = [t for t in measured if t["blind_spot"] == "row1_overfit"]
    volume = [t for t in measured if t["blind_spot"] == "volume_only"]
    elsewhere = [t for t in measured if t["blind_spot"] == "other_field"]
    false_alarm = [t for t in measured if _clean(t["full"]) and not _clean(t["preview"])]

    bar = "#" * 78
    print(bar)
    print(f"#  HEALS THAT PASSED THE ONE-ROW GATE AND WERE BROKEN ON THE FULL PAGE: "
          f"{len(overfit)} of {len(measured)}")
    print(bar)
    for t in overfit:
        p, f = t["preview"], t["full"]
        print(f"  {t['page']}/{t['family']} ({t['collector_id']})")
        print(f"    preview  : {p['rows']} row  {str(p['decision']).upper()} {p['confidence']}/100  "
              f"price looks like {_label(p)} (median {p['price_median']})")
        print(f"    full run : {f['rows']} rows {str(f['decision']).upper()} {f['confidence']}/100  "
              f"price looks like {_label(f)} (median {f['price_median']})  "
              f"codes {','.join(f['codes']) or 'none'}")
    if not overfit:
        print("  None in this sample. Every heal whose preview looked clean was clean on all rows,")
        print("  so P1 - correct on row 1, wrong after it - is UNOBSERVED here, not disproved.")

    if volume:
        print()
        print(f"blind spot, volume-only: {len(volume)} - the price column is intact and the full run")
        print("  failed only on checks a one-row preview cannot run (row count, cardinality). Real,")
        print("  and invisible at the gate, but not an overfit of the price selector.")
        for t in volume:
            print(f"    {t['page']}/{t['family']}: {','.join(t['full']['codes'])}")

    if elsewhere:
        print()
        print(f"blind spot, another field: {len(elsewhere)} - the price column is intact and the")
        print("  break is elsewhere. The gate's one row happened not to show it. Also a real miss,")
        print("  also not P1.")
        for t in elsewhere:
            print(f"    {t['page']}/{t['family']}: {','.join(t['full']['codes'])}")

    if false_alarm:
        print()
        print(f"the gap in the other direction: {len(false_alarm)} trial(s) whose one-row preview")
        print("  looked bad and whose full run was clean. The gate's sample is one row; if that row")
        print("  is unrepresentative - and on a page whose FIRST TILE is the anomaly it is exactly")
        print("  that - rejecting on it discards a good heal. Read these before claiming that")
        print("  preview-based gating is free.")
        for t in false_alarm:
            print(f"    {t['page']}/{t['family']}: preview said {_label(t['preview'])} "
                  f"({str(t['preview']['decision']).upper()}), full run clean")


def _print_integrity(normalised: list[dict], trials: list[dict]) -> None:
    """Was this log gathered under the conditions its conclusions assume?

    Two ways the sample can be quietly worthless, both recorded per trial by `gather` and both
    reported here rather than left for someone to notice: an approve that reached production (so the
    later trials healed a changed collector), and a heal that started from a different template than
    the first one on its collector (so the trials are a chain). Either one means the tally above is
    describing a sequence of dependent events as if they were repeated draws.
    """
    leaked = [t for t in normalised if t["raw"].get("draft_assumption_failed")]
    chained = [t for t in trials if t["raw"].get("started_from_first_template") is False]
    checked = [t for t in trials if t["raw"].get("production_unchanged") is not None]
    print()
    print("integrity of the sample")
    if leaked:
        print(f"  !! {len(leaked)} trial(s) found PRODUCTION CHANGED after an approve. Everything")
        print("     logged after the first of those is a heal of a healed collector, not a sample.")
        dirty = sorted({t["collector_id"] for t in leaked if t["collector_id"]})
        print(f"     collectors left changed, to repair or rebuild by hand: {', '.join(dirty)}")
    elif checked:
        print(f"  production verified unchanged after {len(checked)} approve(s) - the draft")
        print("  assumption held, so committed trials started from the same template.")
    else:
        print("  no committed trials, so nothing was accepted and independence is trivial.")
    # Did `--version dev` actually read the draft? If every committed trial that proposed a real
    # template change produced a draft run indistinguishable from production, the likeliest
    # explanation is that the flag did nothing and the "full measurement" was production all along -
    # in which case every zero in the blind-spot banner is a false negative, not a result.
    changed = [t for t in trials if t["raw"].get("heal_proposed_a_change")
               and t["raw"].get("draft_matches_production") is not None]
    identical = [t for t in changed if t["raw"]["draft_matches_production"]]
    if changed and len(identical) == len(changed):
        print(f"  !! all {len(changed)} committed trial(s) proposed a template change and yet the")
        print("     draft run was indistinguishable from production. Either every heal was a no-op,")
        print("     or `--version dev` did not read the draft and the full runs measured production.")
        print("     Treat the blind-spot count as UNPROVEN until one draft run differs.")
    elif identical:
        print(f"  {len(identical)}/{len(changed)} committed trial(s) changed the template without")
        print("     changing the output - plausible for a good heal, worth a glance in the diff.")

    if chained:
        print(f"  !! {len(chained)} heal(s) started from a different template than the first heal on")
        print("     the same collector - those trials are a chain. Read them in order, not as a tally.")
    elif any(t["raw"].get("template_a_hash") for t in trials):
        print("  every heal started from the same template as the first on its collector.")
    else:
        print("  no template diffs captured (older records) - independence cannot be checked here.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analyse", action="store_true", help="read the log and print the tally (free)")
    ap.add_argument("--page", action="append", default=None, metavar="NAME=URL@COLLECTOR",
                    help="a page under test; repeat the flag for each")
    ap.add_argument("--control", default=None,
                    help="which --page is the clean control (default: the page named 'clean'). "
                         "Without one, no failure can be attributed to page structure.")
    ap.add_argument("--collector", help="c_* id to probe (single-page shorthand)")
    ap.add_argument("--url", help="the page the collector reads (single-page shorthand)")
    ap.add_argument("--page-name", default="unnamed",
                    help="name recorded for the --collector/--url shorthand page")
    ap.add_argument("--repeat", type=int, default=1, help="repetitions per (page, prompt family)")
    ap.add_argument("--prompts", default=None,
                    help=f"comma-separated families (default: all). available: "
                         f"{', '.join(PROMPT_FAMILIES)}")
    ap.add_argument("--commit-and-measure", default=None, metavar="TOKEN",
                    help=f"APPROVE each heal into the draft, run the draft for all rows, measure it, "
                         f"and verify production did not move. Spends credits. Requires the exact "
                         f"token {CONFIRM_TOKEN!r}.")
    ap.add_argument("--page-cost", type=int, default=1, metavar="CREDITS",
                    help="credits billed per load of this page (1 for the testbed, ~97 for the "
                         "96-tile Newegg category page). Used for the estimate only.")
    ap.add_argument("--max-credits", type=int, default=DEFAULT_MAX_CREDITS, metavar="N",
                    help=f"refuse to start, and stop mid-run, past this estimated spend "
                         f"(default {DEFAULT_MAX_CREDITS}). Spend cannot be polled - `budget "
                         f"balance` 403s - so this is arithmetic, not a measurement.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and the credit estimate, call nothing, spend nothing")
    args = ap.parse_args(argv)

    if args.analyse:
        analyse(args)
        return
    if not args.page and not (args.collector and args.url):
        ap.error("give --page NAME=URL@COLLECTOR (repeatable), or --collector with --url, "
                 "or --analyse")
    gather(args)


if __name__ == "__main__":
    main()
