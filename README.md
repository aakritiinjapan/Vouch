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
│       ├── guardian/
│       │   ├── checks.py         ★ tiered validation (structural, distributional, column-swap)
│       │   ├── judge.py          LLM-as-judge on sampled rows (stub → wire Anthropic)
│       │   └── verdict.py        ★ combine checks → confidence score + PASS/FAIL/REVIEW + brief
│       ├── pricing/
│       │   └── engine.py         propose new price from competitor data + rules
│       └── api/
│           └── routes.py         REST endpoints for the dashboard
│   └── tests/
│       ├── test_checks.py        ★ proves the guardian catches a bad heal
│       └── fixtures/sample_runs.json  baseline vs. good vs. swapped heal
├── frontend/                     React + Vite dashboard (Claude Code scaffolds via `npm create vite`)
├── docs/
│   ├── RESEARCH.md               why this idea (hand to teammates)
│   └── DEMO_SCRIPT.md            the 5-minute demo sequence
└── scripts/seed.py               seed demo products + notes on the mock competitor page
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
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../.env   # .env.example lives at the REPO root, one level above vouch/
                                # (or leave MOCK_MODE=true to run entirely offline)
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

See `.env.example` for the variables. `MOCK_MODE=true` runs the entire pipeline against fixtures
with no Bright Data / Anthropic calls — use it for all dev and for a deterministic demo.

---

## 9. Non-goals / guardrails (don't over-build)

- **Don't build "self-healing."** Bright Data provides it. We build the *validation layer* on top.
- **Don't put the heal drama in the seller's face.** Held decisions and honest staleness only.
  The heal event log is a *secondary* panel for the operator, not the headline.
- **Don't ship a generic tracker.** The product is the guardian + the held-decision workflow. The
  GPU/marketplace angle is just the vehicle.
- Keep the vertical narrow (a handful of SKUs, one or two competitor sources) — depth over breadth.
