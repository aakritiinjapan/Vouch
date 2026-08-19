# Vouch

**A repricing copilot that never reprices you off a number it can't verify.**

> Working codename — rename freely. "Vouch" = the tool vouches for every price before it acts on it.

Built for the **Into the Scrape-Verse** hackathon (Bright Data), Aug 17–23 2026.

---

## 1. The one-paragraph pitch

Online sellers reprice their catalog against competitors. That means scraping competitor
prices continuously — and competitor sites change their layout without warning. Bright Data
Scraper Studio *self-heals* when a site changes: it rewrites the extraction so data keeps
flowing. The problem we solve: **a heal can be silently wrong.** It can start pulling the
crossed-out original price instead of the sale price, or shipping cost instead of item price —
right number of rows, right format, wrong meaning. A normal repricer would match that phantom
number and tank the seller's margin. **Vouch is the guardian that validates every self-heal
before it's committed, and holds any price change it can't stand behind.** The seller only ever
acts on numbers Vouch has verified.

Full rationale for why this idea (and not a price tracker) is in [`docs/RESEARCH.md`](docs/RESEARCH.md).

---

## 2. What makes this win (keep this in view while building)

We studied ~6 recent AI hackathons. In **developer/tooling** hackathons (which this is), the
winners are almost always **"guardian" projects** — things that *validate, gate, or verify* an
AI's output — not things that just generate. The single strongest pattern: a **confidence score
+ plain-English risk brief that gates an action** (Microsoft's grand-prize "release gate,"
UiPath's "Gauntlet," a whole sweep of testing/QA winners). Underneath everything, the invariant
is **production-readiness** — the winner always *feels like a finished product.*

Vouch is exactly that archetype, aimed at the one place it feels *natural to an end user* rather
than forced: a user who is **about to commit real money** off the data. The reliability signal
isn't backend plumbing here — it's the headline feature, because it gates the seller's decision.

This maps directly onto the judged criteria:

| Criterion | How Vouch scores it |
|---|---|
| Use of Scraper Studio | The guardian *wraps* Studio's heal loop (run → heal → validate → approve). Studio is the core, not a bolted-on scrape. |
| Reliability & self-healing | The entire product IS the self-healing loop + the validation that makes it trustworthy. |
| Impact | Prevents a seller from repricing off bad data — legible, money-shaped harm avoided. |
| Creativity | "Validate the *meaning* of a heal, not just the shape" — column-swap / distribution drift detection. |
| Technical excellence | Tiered validator (cheap deterministic checks gate the expensive LLM), typed, tested. |
| Presentation | The "held decision" UI makes the guardian visible and demoable. See [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). |

---

## 3. Architecture

```
                 ┌─────────────────────────────────────────────────┐
                 │                    Vouch                         │
                 │                                                  │
  competitor     │   orchestrator.py  (the scrape→guard→price loop) │
  sites ────────▶│        │                                         │
                 │        ├─▶ scraper/brightdata.py                 │
                 │        │     run() / propose_heal() / approve()  │───▶ Bright Data
                 │        │                                         │     Scraper Studio
                 │        ├─▶ guardian/  ◀── the differentiated core │◀───  (heal loop)
                 │        │     checks.py  (tiered validation)       │
                 │        │     judge.py   (LLM-as-judge on sample)  │
                 │        │     verdict.py (confidence score + brief)│
                 │        │                                         │
                 │        └─▶ pricing/engine.py (propose new price) │
                 │                    │                             │
                 │              SQLite (models.py)                  │
                 │                    │                             │
                 │              FastAPI (api/)  ───────────────────▶│──▶ React dashboard
                 └─────────────────────────────────────────────────┘     (decision queue)
```

**The core loop (orchestrator.py):**

1. Run each product's competitor collector (`scraper.brightdata.run`).
2. If the run looks **degraded** (empty / partial / null-spike vs. the stored baseline) →
   trigger a **heal**: `propose_heal()` proposes a fix but **does not commit** (Bright Data's
   heal is human-in-the-loop by default — it stops at an approval gate).
3. **Guardian validates the proposed heal** against the last-known-good baseline
   (`guardian.checks` + `guardian.verdict`). Output: a **confidence score (0–100)** + per-field
   verdict + a plain-English **risk brief**.
   - `PASS` → `approve_heal()` (commit; same collector id) → data is trusted → propose reprice.
   - `FAIL` → reject the heal, keep the old collector, and re-prompt the heal with the
     guardian's own diagnosis.
   - `REVIEW` → the source is marked **unconfirmed**; any reprice touching it is **held**.
4. For trusted data, `pricing.engine` proposes a new price (respecting the floor margin) →
   creates a `RepriceProposal` the seller reviews.

**Why validate *before* approve (not after):** Bright Data does **not** expose programmatic
collector rollback. A wrong approve is expensive to undo. So the only safe place to stand is the
pre-approval gate. This is the whole architectural thesis — build around it.

---

## 4. Tech stack (pinned — don't swap without reason)

- **Backend:** Python 3.11, FastAPI, SQLModel (SQLite), `httpx`.
- **Bright Data:** the `brightdata` CLI (via subprocess) and/or `brightdata-sdk` Python package.
- **LLM judge:** `anthropic` SDK (the semantic backstop; runs on a small sample only).
- **Frontend:** React + Vite + TypeScript + Tailwind. One screen that matters: the decision queue.
- **Tests:** `pytest`. Aim for a real suite around `guardian/` — it's the clean-code story.

---

## 5. Repo layout

```
vouch/
├── README.md                     ← you are here (build brief)
├── .env.example
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py               FastAPI app + routes
│       ├── config.py             env settings (incl. MOCK_MODE)
│       ├── db.py                 SQLite engine/session
│       ├── models.py             ★ data model (Product, RepriceProposal, HealEvent, Baseline…)
│       ├── orchestrator.py       ★ the scrape→guard→price loop
│       ├── scraper/
│       │   ├── brightdata.py     ★ wraps run / heal / approve (+ MOCK_MODE)
│       │   └── baseline.py       capture + store last-known-good profile
│       ├── service.py           ★ the ONLY module that writes rows (persistence + decisions)
│       ├── guardian/
│       │   ├── checks.py         ★ tiered validation (structural, distributional, column-swap)
│       │   ├── judge.py          LLM-as-judge on sampled rows (stub → wire Anthropic)
│       │   └── verdict.py        ★ combine checks → confidence score + PASS/FAIL/REVIEW + brief
│       ├── pricing/
│       │   └── engine.py         propose new price from competitor data + rules
│       └── api/
│           ├── routes.py         REST endpoints for the dashboard
│           └── schemas.py        read models + the builders that assemble them
│   ├── tests/                   90 tests
│   │   ├── test_checks.py        ★ proves the guardian catches a bad heal
│   │   ├── test_guardian_edges.py ★ proves it does NOT cry wolf on legitimate drift
│   │   ├── test_orchestrator.py  the cycle + retry loop, with no database
│   │   ├── test_service.py       the persistence contract, incl. the trust ratchet
│   │   ├── test_api.py           the demo arc, driven over HTTP
│   │   ├── test_brightdata.py    the live CLI path (approval gate, envelope parsing)
│   │   ├── test_pricing.py       the floor-margin clamp
│   │   └── fixtures/sample_runs.json  baseline / degraded run / good heal / swapped heal
│   └── scripts/seed.py           demo products, baseline, and price history
├── frontend/                     React + Vite dashboard (Claude Code scaffolds via `npm create vite`)
└── docs/
    ├── RESEARCH.md               why this idea (hand to teammates)
    ├── DEMO_SCRIPT.md            the 5-minute demo sequence
    ├── BRIGHT_DATA_NOTES.md      Scraper Studio gotchas + the Newegg target, verified
    └── sample_output.json        real collector output (written by scripts/create_collector.py)
```

★ = already scaffolded with real logic or precise signatures. Everything else, build per below.

---

## 6. Instructions for Claude Code

Build in these phases. **Do not skip Phase 0.** After each phase, the stated check must pass.

### Phase 0 — Boot & prove the core offline (do this first)
- Install backend deps; create `.env` from `.env.example`; set `MOCK_MODE=true`.
- Wire `db.py` + `models.py` so the DB initializes.
- **Make `pytest` green.** `tests/test_checks.py` already encodes the central claim: the guardian
  must return `FAIL` on the swapped-price heal and `PASS` on the good heal. If it passes, the
  differentiated core works *before* you've touched Bright Data or the UI.
- ✅ **Check:** `pytest -q` passes; `uvicorn app.main:app` boots and `/health` returns ok.

> Everything downstream can be built and demoed in `MOCK_MODE` against
> `tests/fixtures/sample_runs.json`. This keeps dev deterministic and offline, and means the demo
> never depends on a live site breaking on cue. Only flip `MOCK_MODE=false` once the flow works.

### Phase 1 — The decision queue (the product surface)
- FastAPI endpoints in `api/routes.py`:
  - `GET /products`, `GET /proposals?status=pending|held`, `POST /proposals/{id}/approve`,
    `POST /proposals/{id}/reject`, `GET /heal-events`.
- React dashboard, one primary screen — the **decision queue** (see §7). It must render:
  - a list of pending reprice proposals (bulk-approvable),
  - **held** proposals shown distinctly, each with the plain-English reason + confidence score,
  - a heal-event log using real CLI vocabulary ("heal proposed", "awaiting approval",
    "verdict: rejected — price/shipping swap", "fix approved").
- ✅ **Check:** with seeded mock data, the seller can approve a batch and see a held item with its risk brief.

### Phase 2 — Real Bright Data integration
- Implement `scraper/brightdata.py` against the real CLI/SDK (signatures already stubbed):
  - `run(collector_id, url)` — SDK `client.scraper_studio.run(...)` or `brightdata scraper run`.
  - `propose_heal(collector_id, prompt, url)` — `brightdata scraper heal <id> "<prompt>" --url <url> -o heal.json`; return proposed rows + pending handle.
  - `approve_heal` / `reject_heal` — `brightdata scraper approve` / the API reject call.
- ⚠️ **Confirm two things by testing against a real collector before relying on them:**
  1. that `heal.json` (with `--url`) contains the **proposed rows** pre-approval (the guardian needs them);
  2. the exact reject call (`POST /dca/collectors/{id}/resume_automation_job` with a reject payload).
- ✅ **Check:** create a collector against the mock page (§ DEMO_SCRIPT), run it, get real rows.

### Phase 3 — Close the loop + polish
- `pricing/engine.py`: propose_price respecting `floor_margin`; explain the reason string.
- `guardian/judge.py`: wire the Anthropic LLM-as-judge on a 10–20 row sample; only invoked when
  the cheap checks are ambiguous. Feed its result into `verdict.py`.
- The re-prompt-on-fail loop in `orchestrator.py` (guardian diagnosis → sharper heal prompt).
- Polish the UI to "finished product" standard (empty states, loading, the held-card design).
- ✅ **Check:** full run of `docs/DEMO_SCRIPT.md` works end to end in MOCK_MODE.

---

## 7. The one screen that matters

The dashboard is **exception-based** — it is not a data display, it is a decision queue. The
seller's job is to touch only what needs judgment. Design target:

- **Top:** a batch of routine reprice proposals with an **"Approve all safe changes"** button.
  These are changes Vouch is confident about (high verdict score, within safe margin band).
- **Center (the star):** **Held decisions.** Each is a card, e.g.:

  ```
  ⏸  Reprice held · "MSI RTX 5080 Gaming Trio"
      We found a competitor price of $1,199 — but Newegg's page changed overnight and the
      number we healed to matches their crossed-out original, not the sale price.
      Confidence: 34 / 100   ·   source: newegg.com (unconfirmed)
      [ Investigate ]  [ Approve anyway ]  [ Skip this cycle ]
  ```

  The seller sees a **held decision**, not a healing animation. That's the difference from a
  price tracker: the reliability signal is the feature, because it just protected their margin.
- **Side:** a heal-event log in real Scraper-Studio vocabulary (signals "we understood the tool").

Honest data state, never fake continuity: a held source shows "last confirmed 2h ago" and a
**gap in the price chart**, not an invented straight line.

---

## 8. Environment

```bash
# backend  (from vouch/backend)
python -m venv .venv
source .venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -r requirements.txt
python -m scripts.seed               # 3 products, 1 baseline, 24 price observations
uvicorn app.main:app --reload        # http://127.0.0.1:8000  (/docs for the API)

# frontend  (from vouch/frontend)
npm install
npm run dev                          # http://127.0.0.1:5173, proxies /api to the backend

# tests
cd backend && pytest -q              # 90 tests
```

`.env` is optional - every default is set for offline use (`MOCK_MODE=true`). Copy `.env.example`
from the repo root if you want to fill in tokens. `database_url` resolves to an absolute path under
`backend/`, so it cannot matter which directory you launch from.

See `.env.example` for the variables. `MOCK_MODE=true` runs the entire pipeline against fixtures
with no Bright Data / Anthropic calls — use it for all dev and for a deterministic demo.

---

## 9. How Vouch uses Bright Data Scraper Studio

Scraper Studio is not a bolted-on scrape here - Vouch **wraps its heal loop**, and the product only
exists because of one specific property of that loop.

**The collector.** A custom Scraper Studio collector, created from the CLI with a precise
natural-language field description (item name, sale price, shipping cost, rating, stock), reads a
public competitor listing page. Its first clean run becomes the guardian's **baseline** - a per-field
statistical fingerprint (`guardian/checks.py:profile_run`) stored in the `Baseline` table.

**The loop we wrap** (`orchestrator.run_cycle_for_product`):

| Step | Scraper Studio | Vouch |
|---|---|---|
| 1 | `scraper run` | profile the rows; compare against the baseline |
| 2 | - | if a check fires (`NULL_SPIKE`, `FIELD_MISSING`, `ROW_COUNT_SHIFT`), trigger a heal |
| 3 | `scraper heal` -> stops at the gate, `status: "awaiting_approval"` | read `preview_result` - the rows the fix *would* produce |
| 4 | - | **validate them before committing**: confidence 0-100 + PASS/REVIEW/FAIL + a plain-English brief |
| 5 | `scraper approve <id>` / `... --reject` | commit only what we can vouch for; reject the rest |
| 6 | `scraper heal` again | re-prompt with the guardian's own diagnosis, then re-validate |

**Why the pre-approval gate is the whole thesis.** Bright Data exposes no programmatic collector
rollback, so a wrong `approve` is expensive to undo. The gate is the only safe place to stand - which
is why Vouch validates *before* committing rather than monitoring afterwards.

**The property that makes it possible.** Without `--auto-approve`, `heal` pauses and its envelope
carries `preview_result`: the sample rows the fixed scraper would return. Scraper Studio's own UI
shows only the **code diff** on Accept/Decline. So the CLI/API path surfaces data the approval screen
cannot show a human - and that is exactly the data you need to catch a heal that is *shaped* right
and *meaning* wrong. **We never pass `--auto-approve`**: it commits without the gate, which would
delete the thing this product is.

### The two ways a heal lies, and why one check is not enough

The guardian catches two genuinely different failures, and the second is the reason it has four tiers
rather than three:

| The heal starts reading... | How far off | What catches it | What it costs you |
|---|---|---|---|
| the **shipping cost** as the price | ~100x too low | `COLUMN_SWAP` - the distributions no longer overlap at all | margin: you undercut yourself into the floor |
| the **crossed-out original** as the price | ~14% too high | `VALUE_ORDER_INVERTED` - see below | the sale: you price above the market |

The second one defeats every distributional check, and that is not a tuning problem. A 14% shift will
not move a median past `check_numeric_drift`'s threshold, and `check_column_swap` *deliberately
refuses* to compare two fields whose baselines look that similar - for indistinguishable fields,
"closer to the other one" is noise, not evidence. Loosening either threshold to catch it would start
holding legitimate price drift, which is its own harm.

So Tier 2c uses a different kind of evidence entirely: an **invariant**. A sale price can never exceed
the list price it is discounted from. When that inverts on most rows, it is about as close to proof of
a swap as scraped data offers - and unlike every other check, it needs no baseline, so it protects the
very first run too. `tests/test_value_ordering.py` proves the distributional tier is blind here rather
than just asserting it, so nobody later deletes the check thinking it is redundant.

The two failures also harm you in **opposite directions**, which the held card has to get right:
underpricing destroys margin, overpricing loses the sale. The counterfactual names which one, because
rendering "+$200 per unit" as a margin figure would be straightforwardly wrong.

**Step 6 is the part we are proudest of.** `orchestrator._resharpen_prompt` turns the guardian's
machine-readable finding into the next heal prompt - for a `COLUMN_SWAP` it tells Scraper Studio which
column it grabbed, what median it returned, and what the field's own historical range was. Vouch's
validator writes Scraper Studio's next instruction. Capped at 2 attempts, because each one is a real
heal against real credits and a 3-job AI-Flow concurrency cap.

Operational detail - the CLI's 500-char description cap, the orphaned collectors a failed `create`
leaves behind, the AI-Flow concurrency limit, and the Newegg page quirks the collector has to survive
- is written up in [`docs/BRIGHT_DATA_NOTES.md`](docs/BRIGHT_DATA_NOTES.md).

**Live collector ID:** `c_mszq0z1x27brru3wab` — a custom Scraper Studio collector built from the CLI
against [Newegg's GPU category page](https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96),
extracting name / price / shipping / rating / stock for 96 cards in one run.

**Example structured output:** [`docs/sample_output.json`](docs/sample_output.json) — the real 96-row
run that became the guardian's baseline.
**A real heal at the gate:** [`docs/live_heal_vague.json`](docs/live_heal_vague.json) — an actual
`scraper heal`, captured *at* `awaiting_approval` with its `preview_result` rows and the guardian's
verdict on them, before anything was committed. Reproduce with `python -m scripts.live_heal`.

What that live run did and did not establish, stated plainly:

- ✅ **The architecture holds against the real API.** The gate stopped at `awaiting_approval`, handed us
  `preview_result`, the guardian rendered a verdict on those rows, and we rejected — leaving the
  collector untouched and operational, exactly as the design assumes.
- ✅ **It taught us something the docs omit.** `preview_result` is a *sample* — 1 row against our 96-row
  baseline. That initially broke the volume-dependent checks, which reported the preview size as a
  finding (`Row count changed from 96 to 1`) instead of judging the heal. It is now handled explicitly
  via `is_sample`, and the detection matrix is verified against the real baseline: a one-row preview
  still catches a shipping swap, a null price, a dropped field, and a crossed-out original. See
  [`BRIGHT_DATA_NOTES.md`](docs/BRIGHT_DATA_NOTES.md) §2.
- ⚠️ **The heal we triggered was not a bad one.** Our deliberately vague prompt still produced a correct
  extraction ($519.99 for a Radeon RX 9060 XT), so the guardian passed it — the right answer, not a
  missed detection. The *rejected*-heal path is therefore demonstrated against the fixture, where a
  swap can be produced on demand. We have not manufactured a real bad heal and do not claim to have.

One honest note on the collector's output shape: Scraper Studio named its container after what it found
(`graphics_cards`), nested each product inside it, and returned prices as
`{"value": 299.99, "currency": "USD"}`. That is not wrong, it just is not the flat shape the guardian
profiles — so `scraper/brightdata.py:_rows` normalises it in one place rather than teaching every check
about the wrapper. It also **refuses any non-USD price outright**: `newegg.ca` does not redirect to
`.com` and serves a different catalogue in CAD, so accepting those numbers as USD would silently poison
the price history. `original_price` was *not* captured by this collector (Newegg shows a crossed-out
price on only ~33% of tiles), so `VALUE_ORDER_INVERTED` is exercised against the fixture rather than
live.

---

## 10. AI assistance disclosure

This project was built with **Claude Code** (Anthropic) as the coding agent, driven from the terminal
alongside the Bright Data CLI - the workflow the hackathon's resources page describes.

What the agent did: scaffolded and implemented the persistence layer, REST API, and React dashboard;
wrote the test suite; and researched the Scraper Studio CLI/API surface against Bright Data's docs.

What we did: chose the problem and the architecture - validating a heal at the pre-approval gate, and
placing it inside a repricer so reliability is the headline feature rather than plumbing (see
[`docs/RESEARCH.md`](docs/RESEARCH.md)); made the design calls the agent surfaced, including storing
the counterfactual as one column on the decision rather than as a second observation, the trust
ratchet on baselines, and inverting the demo's break technique once it became clear that an
underspecified *create* prompt would poison the very baseline the guardian judges against; and
reviewed every rule in `guardian/` line by line. We can explain and defend every architectural
decision in this repo.

---

## 11. Non-goals / guardrails (don't over-build)

- **Don't build "self-healing."** Bright Data provides it. We build the *validation layer* on top.
- **Don't put the heal drama in the seller's face.** Held decisions and honest staleness only.
  The heal event log is a *secondary* panel for the operator, not the headline.
- **Don't ship a generic tracker.** The product is the guardian + the held-decision workflow. The
  GPU/marketplace angle is just the vehicle.
- Keep the vertical narrow (a handful of SKUs, one or two competitor sources) — depth over breadth.
