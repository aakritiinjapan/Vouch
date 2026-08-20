# Vouch

**A repricing copilot that never acts on a number it can't verify.**

Built for [Into the Scrape-Verse](https://www.wemakedevs.org/hackathons/scrape-verse) (Bright Data ×
WeMakeDevs), 17–23 August 2026.

> **Live Scraper Studio collector:** `c_mszq0z1x27brru3wab` — a custom collector built from the
> Bright Data CLI against [Newegg's GPU category page](https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96),
> extracting name / price / shipping / rating / stock for 96 graphics cards in a single run.
> Real output: [`vouch/docs/sample_output.json`](vouch/docs/sample_output.json) ·
> A real heal captured at the approval gate: [`vouch/docs/live_heal_vague.json`](vouch/docs/live_heal_vague.json)

![The Vouch console with three reprices held. A ZOTAC RTX 5090 shows −$951.00 per unit of margin
protected, because the healed price of $19.99 matched the competitor's shipping column rather than
their item price.](vouch/docs/screenshot-held.png)

<sub>Three held decisions on real Newegg data. With every source confirmed, the same console is
quiet — see [`screenshot-confirmed.png`](vouch/docs/screenshot-confirmed.png).</sub>

---

## Quickstart

```bash
git clone https://github.com/DeepakReddyVelagala/Vouch.git
cd Vouch
./demo.sh
```

That installs both halves, seeds the database from the real collector's output, and starts the API
on `http://127.0.0.1:8000` and the dashboard on `http://127.0.0.1:5173`. It runs entirely offline —
no Bright Data or Anthropic credentials required.

Prerequisites: Python 3.11+, Node 20+. `make demo` does the same thing if you prefer.

---

## The problem

Sellers reprice their catalogue against competitors, which means scraping competitor prices
continuously — and competitor sites change their layout without warning. Bright Data Scraper Studio
*self-heals* when that happens: it rewrites the extraction so data keeps flowing.

The failure we address is the one underneath that: **a heal can be silently wrong.** It can start
pulling the crossed-out original price instead of the sale price, or the shipping cost instead of
the item price. Right number of rows, right format, right types — wrong meaning. Nothing in the
pipeline reports an error, and a normal repricer happily matches the phantom number.

The real run in this repo makes the stakes concrete. A ZOTAC RTX 5090 lists at **$6,900.00** with
**$19.99** shipping. A heal that quietly swaps those two columns reprices you against a $19.99
competitor — a 345× error that looks perfectly healthy from the outside.

**Vouch validates every proposed heal before it is committed, and holds any price change it can't
stand behind.**

---

## How it uses Scraper Studio

Scraper Studio isn't a bolted-on scrape here — Vouch **wraps its heal loop**, and the product only
exists because of one specific property of that loop.

| Step | Scraper Studio | Vouch |
|---|---|---|
| 1 | `scraper run` | profile the rows; compare against the stored baseline |
| 2 | — | if a check fires (`NULL_SPIKE`, `FIELD_MISSING`, `ROW_COUNT_SHIFT`), trigger a heal |
| 3 | `scraper heal` → stops at the gate, `status: "awaiting_approval"` | read `preview_result` — the rows the fix *would* produce |
| 4 | — | **validate them before committing**: confidence 0–100 + PASS/REVIEW/FAIL + a plain-English brief |
| 5 | `scraper approve <id>` / `… --reject` | commit only what we can vouch for; reject the rest |
| 6 | `scraper heal` again | re-prompt with the guardian's own diagnosis, then re-validate |

**Why the gate is the whole thesis.** Bright Data exposes no programmatic collector rollback, so a
wrong `approve` is expensive to undo. The pre-approval gate is the only safe place to stand — which
is why Vouch validates *before* committing rather than monitoring afterwards.

**The property that makes it possible.** Without `--auto-approve`, `heal` pauses and its envelope
carries `preview_result`: the sample rows the fixed scraper would return. Scraper Studio's own UI
shows only the **code diff** on Accept/Decline. So the CLI/API path surfaces data the approval screen
cannot show a human — exactly the data you need to catch a heal that is *shaped* right and *means*
something wrong. **We never pass `--auto-approve`**; it commits without the gate, which would delete
the thing this product is.

**Step 6 is the part we're proudest of.** `orchestrator._resharpen_prompt` turns the guardian's
machine-readable finding into the next heal prompt — for a `COLUMN_SWAP` it tells Scraper Studio
which column it grabbed, what median it returned, and what that field's own historical range was.
Vouch's validator writes Scraper Studio's next instruction. Capped at 2 attempts, because each one
is a real heal against real credits and a 3-job AI-Flow concurrency cap.

Operational detail — the CLI's undocumented 500-character description cap, the orphaned collectors a
failed `create` leaves behind, the concurrency limit, and the Newegg page quirks the collector has to
survive — is written up in [`vouch/docs/BRIGHT_DATA_NOTES.md`](vouch/docs/BRIGHT_DATA_NOTES.md).

### The two ways a heal lies, and why one check isn't enough

| The heal starts reading… | How far off | What catches it | What it costs you |
|---|---|---|---|
| the **shipping cost** as the price | ~100–345× too low | `COLUMN_SWAP` — the distributions no longer overlap at all | margin: you undercut yourself into the floor |
| the **crossed-out original** as the price | ~14% too high | `VALUE_ORDER_INVERTED` — an invariant, not a statistic | the sale: you price above the market |

The second defeats every distributional check, and that isn't a tuning problem. A 14% shift won't
move a median past `check_numeric_drift`'s threshold, and `check_column_swap` *deliberately refuses*
to compare two fields whose baselines look that similar — for indistinguishable fields, "closer to
the other one" is noise, not evidence. Loosening either threshold to catch it would start holding
legitimate price drift, which is its own harm.

So Tier 2c uses a different kind of evidence: an **invariant**. A sale price can never exceed the
list price it is discounted from. When that inverts on most rows it is about as close to proof as
scraped data offers — and unlike every other check it needs no baseline, so it protects the very
first run too. `tests/test_value_ordering.py` *proves* the distributional tier is blind here rather
than just asserting it, so nobody later deletes the check thinking it's redundant.

The two failures also harm you in **opposite directions**, which the held card has to get right:
underpricing destroys margin, overpricing loses the sale. The counterfactual names which one.

---

## Architecture

```
  competitor        ┌──────────────────────── Vouch ────────────────────────┐
  site ────────────▶│                                                        │
                    │  orchestrator.py — the scrape → guard → price loop      │
  Bright Data       │       │                                                │
  Scraper Studio ◀─▶│       ├─▶ scraper/brightdata.py   run/heal/approve      │
  (heal loop)       │       │                                                │
                    │       ├─▶ guardian/   ◀── the differentiated core       │
                    │       │     checks.py   tiered validation               │
                    │       │     judge.py    LLM-as-judge, REVIEW only       │
                    │       │     verdict.py  confidence + risk brief         │
                    │       │                                                │
                    │       └─▶ pricing/engine.py   propose a new price       │
                    │                 │                                      │
                    │           service.py — the only module that writes      │
                    │                 │                                      │
                    │           SQLite ── FastAPI ──────────────────────────▶ │──▶ React dashboard
                    └────────────────────────────────────────────────────────┘    (decision queue)
```

Three properties are load-bearing:

- **`orchestrator.py` is pure.** It opens no session and commits nothing; `service.py` is the only
  module that writes rows. That's why the entire cycle — including the retry loop — is testable
  against unsaved objects with no database at all.
- **Validation is cost-tiered.** Cheap deterministic checks gate the expensive LLM. The Tier-3 judge
  is invoked only on `REVIEW` — at most one API call per held cycle — and while it may escalate a
  doubt freely, it may only *clear* a distributional one, never a doubt about missing data, since it
  only ever read the rows that were present.
- **The trust ratchet.** Baselines advance only on guardian-confirmed data, so a bad heal can never
  become the reference the next heal is judged against.

---

## The dashboard

One screen, exception-based: it is a decision queue, not a data display. The seller's job is to
touch only what needs judgement.

- **Routine reprice proposals** — confident changes within the safe margin band, bulk-approvable.
- **Held decisions** — the star. Each names the number we refused to act on, the check that caught
  it, a confidence score, and what auto-approving would have cost per unit.
- **Heal event log** — Scraper Studio's loop in its own vocabulary: *heal proposed → awaiting
  approval → verdict → approved and committed*.

Held sources show an **honest gap** in the price chart rather than an interpolated line. The chart is
hand-rolled SVG specifically so the gap cannot be smoothed over by a library default.

Approving a held proposal requires `force=true` and returns `409` without it. That refusal is the
product, not a rail bolted on afterwards.

**Investigate** opens the guardian's own working — the measured evidence behind the verdict, and the
sharpened instruction it handed back to Scraper Studio:

![The Investigate panel showing the guardian's evidence — price now matches the shipping
distribution, median $0.00 against its own historical median of $809.99 — and the re-prompt written
from those measurements.](vouch/docs/screenshot-evidence.png)

The console runs entirely offline: no CDN fonts, no external requests, no telemetry.

---

## Tests

```bash
cd vouch/backend && pytest -q     # 181 tests
```

The suite covers the guardian's four tiers, the orchestrator's retry loop with no database, the
persistence contract including the trust ratchet, the live CLI envelope parsing, and the demo arc
driven over HTTP.

---

## Data sources and compliance

The collector reads a **public** Newegg category page. No authentication, no paywalled or
login-protected content, no personal data, one request per cycle, and nothing is redistributed.

Newegg's `robots.txt` permits the exact paths used here and specifies no crawl delay, while its
Terms of Use contain a general prohibition on automated access. That tension is standard across
major retail and we note it rather than paper over it; the volume, the public nature of the pages,
and the absence of any authenticated or personal data are why we consider this use appropriate.
`www.newegg.com` is pinned and non-USD prices are refused outright, because `newegg.ca` serves a
different catalogue in CAD and accepting those as USD would silently poison the price history.

---

## AI assistance disclosure

This project was built with **Claude Code** as the coding agent, driven from the terminal alongside
the Bright Data CLI — the workflow the hackathon's resources describe.

**What the agent did:** scaffolded and implemented the persistence layer, REST API and React
dashboard; wrote the test suite; and researched the Scraper Studio CLI/API surface against Bright
Data's documentation.

**What we did:** chose the problem and the architecture — validating a heal at the pre-approval gate,
placed inside a repricer so reliability is the headline feature rather than plumbing; made the design
calls the agent surfaced, including storing the counterfactual as one column on the decision rather
than as a second observation, the trust ratchet on baselines, and inverting the demo's break
technique once it became clear an underspecified *create* prompt would poison the very baseline the
guardian judges against; and reviewed every rule in `guardian/` line by line.

We can explain and defend every architectural decision in this repository.

---

## What the live run did and did not establish

Stated plainly, because it matters more than a clean claim:

- ✅ **The architecture holds against the real API.** The gate stopped at `awaiting_approval`, handed
  us `preview_result`, the guardian rendered a verdict on those rows, and we rejected — leaving the
  collector untouched and operational, exactly as the design assumes.
- ✅ **It taught us something the docs omit.** `preview_result` is a *sample* — one row against our
  96-row baseline. That initially broke the volume-dependent checks, which reported the preview size
  as a finding instead of judging the heal. It's now handled explicitly via `is_sample`, and the
  detection matrix is verified against the real baseline: a one-row preview still catches a shipping
  swap, a null price, a dropped field and a crossed-out original.
- ⚠️ **The heal we triggered was not a bad one.** Our deliberately vague prompt still produced a
  correct extraction, so the guardian passed it — the right answer, not a missed detection. The
  *rejected*-heal path is therefore demonstrated by replaying a constructed swap against the real
  96-row baseline, where the failure can be produced on demand. We have not manufactured a real bad
  heal and do not claim to have.
- ⚠️ **`original_price` was not captured by this collector** (Newegg shows a crossed-out price on
  only ~33% of tiles), so `VALUE_ORDER_INVERTED` is exercised against a fixture rather than live
  data.

---

## Repository layout

```
Vouch/
├── demo.sh / Makefile            one-command bootstrap
└── vouch/
    ├── backend/
    │   ├── app/
    │   │   ├── orchestrator.py   the scrape → guard → price loop (pure)
    │   │   ├── service.py        the only module that writes rows
    │   │   ├── guardian/         checks.py · judge.py · verdict.py
    │   │   ├── pricing/engine.py floor-margin-respecting price proposals
    │   │   ├── scraper/          brightdata.py (CLI wrapper) · baseline.py
    │   │   ├── api/              routes.py · schemas.py
    │   │   └── models.py         Product · Baseline · RepriceProposal · HealEvent
    │   ├── scripts/              seed · reset_db · create_collector · live_heal
    │   └── tests/                181 tests
    ├── frontend/                 React + Vite + TypeScript dashboard
    └── docs/
        ├── BRIGHT_DATA_NOTES.md  Scraper Studio traps, measured against the live API
        ├── DEMO_SCRIPT.md        the demo walkthrough
        ├── LIVE_CAPTURE.md       how to film the live collector and heal
        ├── MOTIVATION.md         why this problem
        ├── sample_output.json    the real 96-row collector run
        └── live_heal_vague.json  a real heal captured at the approval gate
```

Licensed under the terms in [`vouch/LICENSE`](vouch/LICENSE).
