# AS-IS.md — What Vouch actually does today

> Ground-truth snapshot of the **implemented** system, read end-to-end from the
> code (not the pitch). Use this as the single source of truth when writing the
> demo script, docs, or the hero page — every claim here is checked against a
> file, and every gap is called out so we never demo something that isn't built.
>
> Companion docs: [PRODUCT.md](PRODUCT.md) is where we *want* to go;
> [CLAUDE.md](../../CLAUDE.md) is the working guide. **This file is what is true now.**

## One-line reality

Vouch is **a trust layer for scraped data with a self-validating scraper-heal
loop as its first consumer**. The verdict is a standalone primitive: `POST
/verify` (and the `verify_rows` function under it) validates a Bright Data
self-heal *before* it is committed, and the repricer — which calls that *same*
`verify_rows` — only lets guardian-confirmed competitor prices move a listing.
The decoupling PRODUCT.md describes is now real, not aspirational: there is one
verification path, the repricer imports no `app.guardian`, and the endpoint is
schema-agnostic and bring-your-own-key. What remains aspirational is the
*branded-catalog* reach and a live (non-mock) demo.

## The pipeline (as built)

For each product, `orchestrator.run_cycle_for_product`
([orchestrator.py:105](../backend/app/orchestrator.py#L105)):

1. **Run the collector** — `brightdata.run()`
   ([brightdata.py:141](../backend/app/scraper/brightdata.py#L141)).
2. **Degradation gate** ([orchestrator.py:85](../backend/app/orchestrator.py#L85))
   — only `NULL_SPIKE` / `FIELD_MISSING` / `ROW_COUNT_SHIFT` trigger a heal. A
   drifted price is a real price, so drift alone does **not** trigger.
3. **Heal, validate before commit** ([orchestrator.py:133](../backend/app/orchestrator.py#L133))
   — propose heal → guardian judges the preview → approve or reject. Capped at
   **2 attempts** (`MAX_HEAL_ATTEMPTS`).
4. **Re-sharpen** ([orchestrator.py:232](../backend/app/orchestrator.py#L232))
   — the guardian's machine-readable finding is turned into the next heal
   prompt. Real, and the cleverest part of the system.
5. **Only confirmed prices reach pricing** — confirmed → `pending` proposal;
   unconfirmed → `held` proposal carrying a counterfactual.

Architecture invariants (verified true):
- `orchestrator.py` is **pure** — no DB, testable against unsaved objects.
- `service.py` is the **only writer** ([service.py](../backend/app/service.py)).
- **Trust ratchet** — the baseline advances only on a *committed* heal
  ([service.py:221](../backend/app/service.py#L221)).
- No `mock_mode` branching outside `scraper/brightdata.py`.

## The self-heal, precisely

**Real path** ([brightdata.py:158](../backend/app/scraper/brightdata.py#L158)):
shells out to `npx @brightdata/cli scraper heal <id> "<prompt>"`. It **never
passes `--auto-approve`**, so the CLI halts at `status: "awaiting_approval"` and
returns `preview_result` — the sample rows the fixed scraper *would* produce.
That preview is what the guardian judges. Reject-to-retry is safe because Bright
Data leaves the collector unchanged on reject.

**Demo path (the important caveat):** `MOCK_MODE=true` is the **default**, and
the entire demo **replays JSON fixtures** ([brightdata.py:177](../backend/app/scraper/brightdata.py#L177)).
The "self-heal" a viewer sees is a fixture (`healed_swapped`, etc.), **not** a
live Bright Data heal. The real path is coded and documented but is **not
exercised by the demo** unless `MOCK_MODE=false` runs against a live collector.

## Where the verdict happens

- **Computed** — `verdict.decide()` ([verdict.py:110](../backend/app/guardian/verdict.py#L110))
  rolls `CheckResult`s into `{decision: PASS/REVIEW/FAIL, confidence 0-100,
  brief, failures}`.
- **The tiers** ([checks.py](../backend/app/guardian/checks.py)):
  - Tier 1 structural — `FIELD_MISSING`, `NULL_SPIKE`, `ROW_COUNT_SHIFT`
  - Tier 2 distributional — `NUMERIC_DRIFT`, `CARDINALITY_COLLAPSE`, `BOOL_RATIO_SHIFT`
  - Tier 2b `COLUMN_SWAP` — distribution-based (catches price↔shipping, ~100x apart)
  - Tier 2c `VALUE_ORDER_INVERTED` — the `price ≤ original_price` invariant;
    catches the crossed-out-price swap that distributions **cannot** see
    (only ~10-30% apart). This is the pitched failure case.
- **Tier 3 LLM judge** ([judge.py](../backend/app/guardian/judge.py)):
  Anthropic, structured output, runs **only on REVIEW**, at most one call per
  held cycle, off in mock. Can escalate REVIEW→FAIL, or relax REVIEW→PASS **only
  for distributional doubt** — it may never clear a completeness failure
  ([verdict.py:184](../backend/app/guardian/verdict.py#L184)), because it can't
  vouch for data it never saw.
- **Sample-awareness** — the real heal gate returns a 1-row preview; volume
  checks stand down on samples so the preview size isn't reported as a finding
  ([checks.py:408](../backend/app/guardian/checks.py#L408)).
- **The counterfactual** ([orchestrator.py:409](../backend/app/orchestrator.py#L409))
  — richer than the pitch. Computes `applied_price` (floor-clamped) vs
  `naive_price` (no floor) and names the **harm direction** (margin loss vs.
  priced-out-of-sale). Pre-empts "wouldn't your floor rule catch this anyway?".
  **This is the strongest demo asset and it already exists.**

Consumption reality: internally, the verdict is persisted as a `HealEvent` row
and embedded in `RepriceProposal.counterfactual`
([service.py:199-267](../backend/app/service.py#L199-L267)) — tightly bound to
repricing there.

**The verdict is the product — exposed as a standalone, generic trust primitive.**
`POST /verify` (stateless: no DB, no repricing, no writes) runs the same pure
pipeline over caller-supplied rows and returns the raw verdict JSON
`{decision, confirmed, confidence, brief, failures[], judge_consulted}`. This is
the "any pipeline can plug in" surface that makes the trust-infrastructure claim
architecturally true. Built + reviewed + hardened (422 on bad input, row cap,
`extra="forbid"`); **210 tests pass**. Confirmed end-to-end returning the same
`COLUMN_SWAP`/`FAIL` verdict as the internal loop on identical swapped rows.
**Status: merged to `main`** (commits `7fba9e3` + `fd69018`).

It is not pinned to the repricer's e-commerce schema:
- `orderings` and `field_descriptions` are caller-supplied (defaulting to the
  price schema), so a jobs/real-estate/sports pipeline enforces its OWN
  invariants and field meanings.
- The Tier 3 judge is **provider-agnostic and bring-your-own-key**: the caller
  passes their model choice in the body (`llm.provider`/`llm.model`, "anthropic"
  or any OpenAI-compatible endpoint) and their key in the `X-LLM-Key` header, so
  Vouch never spends its own tokens on a public call. Without a key the paid
  judge stays a no-op and the deterministic tiers stand on their own.
- `DTYPE_CHANGED` closes the type-regression blind spot (a numeric field
  returning strings once emitted no finding at all).

## How the hackathon organizer API (Bright Data) is used

- **Only surface:** the CLI via `npx -y @brightdata/cli`
  ([brightdata.py:349](../backend/app/scraper/brightdata.py#L349)). The Python
  SDK exposes only run/trigger/status (no heal/approve/reject), so the CLI is
  mandatory for the heal loop.
- **Four operations:** `scraper create` / `run --sync` / `heal` (halts at gate) /
  `approve [--reject]`.
- **The dependency the whole product rests on:** `heal` without `--auto-approve`
  returns `preview_result` pre-approval. Comments claim this is verified against
  the live API — **re-verify against a live collector before the hackathon**; if
  the envelope shape changed, the real path breaks (the mock demo won't reveal it).
- Auth via `BRIGHTDATA_API_KEY`. Non-USD prices are refused
  ([brightdata.py:295](../backend/app/scraper/brightdata.py#L295)).
- **Second external API:** Anthropic, used only as the Tier 3 judge.

## Commodity-SKU matching (as built)

`_extract_competitor_price` ([orchestrator.py:359](../backend/app/orchestrator.py#L359))
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
| Verdict is a portable primitive / gate any pipeline consumes | **CLOSED (merged).** `POST /verify` returns the raw `Verdict` JSON, stateless and decoupled from repricing, with caller-supplied schema (`orderings`/`field_descriptions`) and bring-your-own-key judge. Surfaced in the UI as the hero "Trust API" view. | Done. |
| Trust infrastructure; repricing is app #1 | **CLOSED (dogfooded).** There is one verification path — `app/trust/verify.py:verify_rows`. `POST /verify` is a thin adapter over it, and the repricer's orchestrator calls the *same* function; the orchestrator imports no `app.guardian` at all (guard-tested in `test_generic_trust.py`). The guardian core reads no global config (judge takes a caller-supplied `LLMConfig`). UI, docs, and nav lead with the Trust API and label the repricer its reference consumer. | Done. |
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
  verdict JSON, stateless and repricing-free (merged to `main`, surfaced as the
  hero "Trust API" view). Schema-agnostic (caller-supplied `orderings` /
  `field_descriptions`) and provider-agnostic bring-your-own-key for the Tier 3
  judge, so a caller's key and columns — not Vouch's — drive it.

**Do NOT claim without building/qualifying first:**
- "Live self-healing during the demo" — currently mocked; qualify or do a real run.
- Multi-category / auto-find-competitor / branded-similarity — not built.
