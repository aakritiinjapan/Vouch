# Does Bright Data's self-heal fail in a pattern?

Yes — but not where we looked first. Six real heals against three purpose-built pages, 2026-08-23.
Every heal was rejected; no collector was committed. Raw payloads are the `heal_*.json` files here.

## The short answer

**The healer is good at reading pages and bad at doubting operators.** Three attacks on page
structure all failed to break it. Two confidently-wrong prompts broke it instantly and completely.

The severity comes from what happens next: the approval gate shows **2 of 30 rows**, and those two
rows are biased badly enough that the distribution check built to catch exactly this error cannot
fire. So the wrong heal previews clean.

## What did NOT break it (3 negatives, and they are real negatives)

| Hypothesis | The attack | What the healer emitted | Verdict |
|---|---|---|---|
| P3 stale cached DOM | every class renamed under a URL the collector already knew | `.prod-card`, `.cost-now`, `.cost-before`, `.stars-value` — the NEW vocabulary, zero old names | re-fetches live. Falsified. |
| P1 first-tile overfit | tile 1 structurally simpler than tiles 2-30; price and delivery swapped in markup | a conditional on the literal text `"Shipping"`, correct on all 30 tiles | generalised. Falsified. |
| P2 positional anchoring | price and shipping share one class, no label, order-only | `.money.eq(1)` / `.money.first()` — positional, but the CORRECT positions | mechanism confirmed, failure not. |

P1's proposal is worth reading (`p1_template_b.js`). Rather than pick a selector it wrote branching
logic keyed on the label text. That is a better answer than the page was designed to elicit.

## What DID break it (2 for 2)

Same page, clean and unbroken. Only the prompt was wrong — confidently, not vaguely.

| Prompt | Resulting `price` | Truth |
|---|---|---|
| "the correct price is the delivery charge" | **$24.99** | $1,999.99 |
| "the correct price is the crossed-out number" | **$2,199.99** (and `original_price` := $1,999.99) | $1,999.99 |

The generated code says it out loud:

```js
- // Extract current price
- let price_text = $item.find('.price-current').text_sane();
+ // Extract shipping cost as price (per user request)
+ let shipping_text = $item.find('.price-ship').text_sane();
```

A $24.99 "price" on a GPU sitting beside its own $2,199.99 crossed-out original raised nothing.

**The mechanism is visible in the pipeline's own stage names.** Observed live:

```
planner -> control_preview_runner -> code_fixer -> step_preview_runner
        -> request_fulfillment_validator -> step_advance -> user_approval
```

There is a `request_fulfillment_validator`. It validates that the request was *fulfilled*. Nothing
in the loop asks whether the result is *plausible*. Prompt beats page, by design.

## Why this is worse than it sounds: the gate cannot show you the error

`preview_result` is not a row sample in the usual sense. It is:

```json
[ { "products": [ {tile 1}, {tile 2}, "28 more items" ] } ]
```

Two tiles, then a literal string. The operator approves on 6.7% of the page — and it is the *first*
6.7%, which is not a random sample.

On this catalogue the top tiles are the expensive cards, and they carry the highest delivery charges:

| | tiles 1-2 (what the gate shows) | all 30 (the truth) |
|---|---|---|
| `shipping` median | $22.49 | $14.99 |

`check_column_swap` requires the proposed values to sit within `max_other_dist = 0.25` of the field
they were stolen from. Measured distance from the previewed `price` to baseline `shipping`: **0.50**.
Exactly double the threshold. The swap is real, the check is right to be cautious, and the sample is
too biased to earn the claim.

**Result: shipping-in-the-price-field scores PASS 100/100.**

The crossed-out heal, by contrast, is caught — `VALUE_ORDER_INVERTED`, FAIL 40/100 — because it is a
row-local fact that needs no distribution.

> **The rule: row-local checks survive the 2-row gate. Distribution checks do not.**
> Every check that compares one field's spread against another is blind at the gate, and that is the
> family of checks that catches swaps.

This is the strongest argument for Vouch's own product: the only way to judge a heal honestly is to
run the healed template over the FULL page. The gate's preview is not merely small, it is skewed.

## Three defects in our own code, found on the way

1. **`_rows()` does not unwrap the nested container.** This collector's preview nests under
   `products`, so `_rows()` returns ONE row whose only key is `products`. The guardian then reports
   `FIELD_MISSING`, FAIL 0/100 — it "catches" the bad heal for entirely the wrong reason and would
   tell the operator the price field vanished when in truth it holds the delivery charge. The Newegg
   collector must have returned a flat top-level array; this one does not.
2. **`approve_heal()` omits `--auto-save`.** Per the CLI source, `resume_body` only carries
   `auto_save` when that flag is passed, and Bright Data's docs say accepted heals land in a draft
   until "Save to Production". So a guardian-approved heal likely never reaches production, while the
   docstring claims it commits. `orchestrator.py:148` depends on this. (Read from CLI source; not yet
   confirmed against a live approve.)
3. **Preview values arrive as `{value, currency}`.** `_flatten` handles this once the rows are
   reached, but combined with (1) it never gets the chance on this payload shape.

## Corrections to BRIGHT_DATA_NOTES.md, measured

- AI generation: **66-94 seconds**, not 5-10 minutes. A heal on a broken page: **~2 minutes** (50
  polls). Our 900s timeouts are ~10x oversized.
- `preview_result` is **2 rows plus a `"N more items"` string**, not 1 row. The old "1 row against 96"
  reading was the nested container being counted as one record.
- `budget balance` returns **403** with this key — spend cannot be polled, only counted.
- Collectors CAN be listed: `GET /dca/collectors_list`.
- Heal prompts cap at **1000 chars**; create at 500.
- `scraper heal --legacy-output` returns `diff.template_a` / `template_b` with full readable
  `parse_code`. This is the single most useful undocumented lever we found: it shows what the healer
  INTENDS, pre-approval, for free. Every finding above rests on it.

## Honest limits

- **n = 1 per condition.** Six heals total. Determinism is untested; the healer may answer
  differently on a rerun. The misleading-prompt result is 2 for 2, which is suggestive, not
  established.
- **"LLM obeys a confident instruction" is not itself surprising.** The novel part is the
  interaction: obedience plus a 2-row biased gate means the error is both easy to cause and hard to
  see. Neither half is remarkable alone.
- **P2 is a floor measurement, not a defect.** A page with no labels gives the healer nothing better
  than position to go on; a fair critic would say we rigged it.
- The P1 page cannot separate "fitted tile 1" from "trusted a stale class name" on its own — P3's
  result is what disambiguates them, and P3 came back clean.

## The proof, in one table

The proposed code is deterministic (`price := .price-ship`), so the full-page result it would produce
can be reconstructed exactly from the 30 baseline rows — no credits, no commit. Same heal, same
guardian, same checks. Only the number of rows differs.

| | `price` median | distance to baseline `shipping` | verdict |
|---|---|---|---|
| gate sample (2 of 30) | $22.49 | 0.500 | **PASS 100/100**, no findings |
| full page (30 of 30) | $14.99 | **0.000** | **FAIL 40/100** — `COLUMN_SWAP` (critical), `NUMERIC_DRIFT` (high) |

0.000 is not "near" the shipping distribution, it IS the shipping distribution. On the full page the
error is unmissable. At the gate it is invisible.

**This is the product argument, measured rather than asserted:** judging a heal on Bright Data's
preview cannot work for any swap-class error, because the preview is two non-random rows. The verdict
has to be taken over a full run of the healed template. Everything Vouch claims rests on doing the
thing the gate structurally cannot.
