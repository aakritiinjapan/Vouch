# AS-IS.md — What Vouch actually does today

> Ground-truth snapshot of the **implemented** system, read end-to-end from the
> code (not the pitch). Use this as the single source of truth when writing the
> demo script, docs, or the hero page — every claim here is checked against a
> file, and every gap is called out so we never demo something that isn't built.
>
> Companion docs: [PRODUCT.md](PRODUCT.md) is where we *want* to go;
> [CLAUDE.md](CLAUDE.md) is the working guide. **This file is what is true now.**

## One-line reality

Vouch is **a repricing copilot with a self-validating scraper-heal loop**. The
guardian validates a Bright Data self-heal *before* it is committed, and only
guardian-confirmed competitor prices are allowed to move a listing. It is well
engineered and the core loop works. It is **not yet** the decoupled "trust
layer / verdict-as-a-primitive" platform described in PRODUCT.md — that framing
is aspirational.

## The pipeline (as built)

For each product, `orchestrator.run_cycle_for_product`
([orchestrator.py:105](vouch/backend/app/orchestrator.py#L105)):

1. **Run the collector** — `brightdata.run()`
   ([brightdata.py:141](vouch/backend/app/scraper/brightdata.py#L141)).
2. **Degradation gate** ([orchestrator.py:85](vouch/backend/app/orchestrator.py#L85))
   — only `NULL_SPIKE` / `FIELD_MISSING` / `ROW_COUNT_SHIFT` trigger a heal. A
   drifted price is a real price, so drift alone does **not** trigger.
3. **Heal, validate before commit** ([orchestrator.py:133](vouch/backend/app/orchestrator.py#L133))
   — propose heal → guardian judges the preview → approve or reject. Capped at
   **2 attempts** (`MAX_HEAL_ATTEMPTS`).
4. **Re-sharpen** ([orchestrator.py:232](vouch/backend/app/orchestrator.py#L232))
   — the guardian's machine-readable finding is turned into the next heal
   prompt. Real, and the cleverest part of the system.
5. **Only confirmed prices reach pricing** — confirmed → `pending` proposal;
   unconfirmed → `held` proposal carrying a counterfactual.

Architecture invariants (verified true):
- `orchestrator.py` is **pure** — no DB, testable against unsaved objects.
- `service.py` is the **only writer** ([service.py](vouch/backend/app/service.py)).
- **Trust ratchet** — the baseline advances only on a *committed* heal
  ([service.py:221](vouch/backend/app/service.py#L221)).
- No `mock_mode` branching outside `scraper/brightdata.py`.

## The self-heal, precisely

**Real path** ([brightdata.py:158](vouch/backend/app/scraper/brightdata.py#L158)):
shells out to `npx @brightdata/cli scraper heal <id> "<prompt>"`. It **never
passes `--auto-approve`**, so the CLI halts at `status: "awaiting_approval"` and
returns `preview_result` — the sample rows the fixed scraper *would* produce.
That preview is what the guardian judges. Reject-to-retry is safe because Bright
Data leaves the collector unchanged on reject.

**Demo path (the important caveat):** `MOCK_MODE=true` is the **default**, and
the entire demo **replays JSON fixtures** ([brightdata.py:177](vouch/backend/app/scraper/brightdata.py#L177)).
The "self-heal" a viewer sees is a fixture (`healed_swapped`, etc.), **not** a
live Bright Data heal. The real path is coded and documented but is **not
exercised by the demo** unless `MOCK_MODE=false` runs against a live collector.

## Where the verdict happens

- **Computed** — `verdict.decide()` ([verdict.py:110](vouch/backend/app/guardian/verdict.py#L110))
  rolls `CheckResult`s into `{decision: PASS/REVIEW/FAIL, confidence 0-100,
  brief, failures}`.
- **The tiers** ([checks.py](vouch/backend/app/guardian/checks.py)):
  - Tier 1 structural — `FIELD_MISSING`, `NULL_SPIKE`, `ROW_COUNT_SHIFT`
  - Tier 2 distributional — `NUMERIC_DRIFT`, `CARDINALITY_COLLAPSE`, `BOOL_RATIO_SHIFT`
  - Tier 2b `COLUMN_SWAP` — distribution-based (catches price↔shipping, ~100x apart)
  - Tier 2c `VALUE_ORDER_INVERTED` — the `price ≤ original_price` invariant;
    catches the crossed-out-price swap that distributions **cannot** see
    (only ~10-30% apart). This is the pitched failure case.
- **Tier 3 LLM judge** ([judge.py](vouch/backend/app/guardian/judge.py)):
  Anthropic, structured output, runs **only on REVIEW**, at most one call per
  held cycle, off in mock. Can escalate REVIEW→FAIL, or relax REVIEW→PASS **only
  for distributional doubt** — it may never clear a completeness failure
  ([verdict.py:184](vouch/backend/app/guardian/verdict.py#L184)), because it can't
  vouch for data it never saw.
- **Sample-awareness** — the real heal gate returns a 1-row preview; volume
  checks stand down on samples so the preview size isn't reported as a finding
  ([checks.py:408](vouch/backend/app/guardian/checks.py#L408)).
- **The counterfactual** ([orchestrator.py:409](vouch/backend/app/orchestrator.py#L409))
  — richer than the pitch. Computes `applied_price` (floor-clamped) vs
  `naive_price` (no floor) and names the **harm direction** (margin loss vs.
  priced-out-of-sale). Pre-empts "wouldn't your floor rule catch this anyway?".
  **This is the strongest demo asset and it already exists.**

Consumption reality: internally, the verdict is persisted as a `HealEvent` row
and embedded in `RepriceProposal.counterfactual`
([service.py:199-267](vouch/backend/app/service.py#L199-L267)) — tightly bound to
repricing there.

**NEW — the verdict is now also exposed as a standalone trust primitive.**
`POST /verify` (stateless: no DB, no repricing, no writes) runs the same pure
pipeline over caller-supplied rows and returns the raw verdict JSON
`{decision, confirmed, confidence, brief, failures[], judge_consulted}`. This is
the "any pipeline can plug in" surface that makes the trust-infrastructure claim
architecturally true. Built + reviewed + hardened (422 on bad input, row cap,
`extra="forbid"`); **200 tests pass**. Confirmed end-to-end returning the same
`COLUMN_SWAP`/`FAIL` verdict as the internal loop on identical swapped rows.
**Status: committed on branch `feat/trust-verify-endpoint`, not yet merged to
`main`** (a teammate PR + real-run review is planned).

## How the hackathon organizer API (Bright Data) is used

- **Only surface:** the CLI via `npx -y @brightdata/cli`
  ([brightdata.py:349](vouch/backend/app/scraper/brightdata.py#L349)). The Python
  SDK exposes only run/trigger/status (no heal/approve/reject), so the CLI is
  mandatory for the heal loop.
- **Four operations:** `scraper create` / `run --sync` / `heal` (halts at gate) /
  `approve [--reject]`.
- **The dependency the whole product rests on:** `heal` without `--auto-approve`
  returns `preview_result` pre-approval. Comments claim this is verified against
  the live API — **re-verify against a live collector before the hackathon**; if
  the envelope shape changed, the real path breaks (the mock demo won't reveal it).
- Auth via `BRIGHTDATA_API_KEY`. Non-USD prices are refused
  ([brightdata.py:295](vouch/backend/app/scraper/brightdata.py#L295)).
- **Second external API:** Anthropic, used only as the Tier 3 judge.

## Commodity-SKU matching (as built)

`_extract_competitor_price` ([orchestrator.py:359](vouch/backend/app/orchestrator.py#L359))
matches our product to a scraped row by name in three passes (exact-normalised →
containment → token overlap ≥ 0.6), and **refuses on ambiguity** rather than
guessing. This bakes in the commodity-SKU wedge and its "refuse rather than
mis-price" stance.

## Surfaces that exist (API)

`app/api/routes.py`:
- `GET /products`, `GET /products/{id}/history` (chart; competitor price is null
  on unconfirmed cycles so the gap is in the data itself)
- `GET /proposals`, `POST /proposals/{id}/approve` (held requires `force=true`,
  else **409** — the refusal *is* the product), `POST /proposals/{id}/reject`,
  `POST /proposals/approve-safe`
- `GET /heal-events` (operator log)
- `POST /cycles/run` (demo remote control; simulate hints are mock-only and
  dropped with a warning when `MOCK_MODE` is off)
- `GET /demo/hints`, `POST /demo/reset`

## Data model (SQLite, 5 tables)

Product · CompetitorObservation (`confirmed=False` when unverified) ·
RepriceProposal (`pending`→`approved`/`rejected`/`held`/`superseded`, carries
`counterfactual`) · HealEvent (`primary_check_code`, `evidence`, `attempt`,
`cycle_id`) · Baseline (advances only on confirmed data).

## Gaps between PRODUCT.md and reality

| PRODUCT.md claim | Reality | Effort to close |
|---|---|---|
| Verdict is a portable primitive / gate any pipeline consumes | **CLOSED (on branch).** `POST /verify` now returns the raw `Verdict` JSON, stateless and decoupled from repricing. Committed on `feat/trust-verify-endpoint`, pending merge. | Merge the branch + surface it in the UI (dedicated "Trust API" view). |
| Trust infrastructure; repricing is app #1 | Code is **a repricer**, not a trust layer with repricing plugged in. Separation is conceptual, not architectural. | Follows from the endpoint above + framing. |
| Live self-heal disaster demo | Demo is **fixture replay** (`MOCK_MODE` default). Real path exists but untested in demo flow. | Decision, not code: rehearse mocked, do one real run + screen-record as backup. |
| Commodity-SKU wedge | **Already built** (name-match, refuse-on-ambiguity). | Done. |
| Quantified counterfactual | **Fully real, exceeds the doc.** | Done. |
| Branded-similar | Nothing exists (correctly — roadmap). | N/A (slide only). |

## For demo / hero-page authors — what is safe to claim

**Safe to claim (built and true):**
- Validates a scraper self-heal *before* it commits, using a real pre-approval
  preview from Bright Data.
- Catches silent field swaps distributions can't see (crossed-out price via the
  ordering invariant).
- Refuses to reprice on unverified data (`held` + 409-on-approve).
- Turns each rejection into a sharper re-heal prompt automatically.
- Quantifies the disaster prevented (floor-clamped vs. naive counterfactual,
  with harm direction).
- Only guardian-confirmed prices advance the baseline (trust ratchet).

- **A trust layer any pipeline can plug into** — `POST /verify` returns the raw
  verdict JSON, stateless and repricing-free (on `feat/trust-verify-endpoint`,
  pending merge). Safe to claim once merged; until then, demo from the branch.

**Do NOT claim without building/qualifying first:**
- "Live self-healing during the demo" — currently mocked; qualify or do a real run.
- Multi-category / auto-find-competitor / branded-similarity — not built.
