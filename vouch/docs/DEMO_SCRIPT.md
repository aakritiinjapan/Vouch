# Demo script (≈5 minutes)

Goal: make the guardian *visible* and the value *legible in money*. The judges should watch a bad
self-heal get caught before it costs the seller margin.

## The core beat (memorize this arc)

> Normal repricing → a competitor site changes → the scraper heals but heals *wrong* → **Vouch
> catches it and holds the price** → show what would've happened if it hadn't → fix and resume.

## Triggering the "break" legitimately

You can't make a real site redesign on cue. Three honest ways to trigger the heal — pick one, and
say plainly which you're doing (judges see this constantly; it's not faking data):

- **A — Self-hosted mirror (default, most reliable).** Snapshot a real listing page's HTML, host it
  as a static "v1", then deploy a "v2" with the price markup moved and a **shipping-cost element
  placed where a naive heal will grab it**. Narrate: "this is a mirror of the real layout with the
  markup changed, so we can trigger healing on demand." Deterministic — safe against demo-day flake.
- **B — Wayback vs. live.** Build the collector against an old Archive.org snapshot, run/heal against
  the current live site. The layout difference is 100% real. Risk: archived CSS/JS can be messy.
- **C — Underspecified *heal* prompt (what we do).** Create the collector with a **precise**
  description so the first extraction is correct — **that run becomes the baseline** — then heal it
  with a deliberately **vague** prompt (the kind a hurried operator actually writes: *"the price
  field looks wrong, re-capture the price near the delivery info"*). The heal grabs the shipping
  cost, and the `awaiting_approval` envelope's real `preview_result` carries the swap. Zero hosting,
  a real public page throughout, and a genuinely real heal.
  > ⚠️ Do **not** underspecify the *create* step instead. Vouch validates a heal against a
  > last-known-good baseline, so if the first extraction is the wrong one, the bad data *is* the
  > baseline — and the guardian would flag the correct fix as the drift. The order matters.

> **Rehearse in `MOCK_MODE`, qualify with a live collector.** The dashboard's *Simulate a bad heal*
> and *Re-prompt & resume* buttons drive the whole arc deterministically off fixtures, so the demo
> never depends on the network. But the submission rules require **at least one live `c_*` Collector
> ID as proof of execution**, and a custom Scraper Studio scraper — so technique **C** is not
> optional polish, it is what qualifies the entry. Build the collector early; demo off mock.

## Screen-by-screen

**0:00 — The product (15s).** Vouch dashboard: a few GPUs, current prices, a small batch of routine
reprice proposals. "Sellers reprice against competitors all day. Vouch proposes changes — but only
off data it can vouch for."

**0:30 — Normal cycle (30s).** Click **Approve all safe changes**. Prices update. "Routine changes
flow through in one click. The point of Vouch is what happens when the data *can't* be trusted."

**1:00 — The break (45s).** Trigger it (technique A). Show the event log: `run: price null on 6/8
rows → heal proposed → awaiting approval`. "Newegg redesigned overnight. Scraper Studio healed
itself automatically — the data's flowing again." *(beat)* "But watch what it healed *to*."

**1:45 — The catch (60s) — the heart of it.** The guardian runs. A **held card** appears:

```
⏸  Reprice held · "MSI RTX 5080 Gaming Trio"
    The healed price ($19.99) matches this competitor's SHIPPING column, not their item price.
    Confidence: 40 / 100   ·   source: newegg-mirror (unconfirmed)   ·   check: COLUMN_SWAP
    [ Investigate ]   [ Approve anyway ]   [ Skip this cycle ]
```

"The heal *worked* — right rows, right format. But it silently swapped price and shipping. A normal
repricer would now match a $20 competitor and destroy the margin. Vouch caught it and **held the
change** — because we never reprice off a number we can't verify."

**2:45 — The counterfactual (45s).** Expand *"What if we'd auto-approved this?"*

Lead with the honest number: **−$165.98 per unit**, margin **19.2% → 7.4%**. Our own floor rule would
have clamped the price to **$1,134.00**, not followed the competitor down to $20 — say so, because it
pre-empts the first question a sharp judge will ask. Then land the point: *"a repricer **without** a
floor rule goes to $19.98 — margin −5,155%. A floor caps the disaster; only verifying the number
prevents the damage."*

The chart shows the honest gap for the held cycle — a hole in the data, not an invented straight
line — with the counterfactual dashed off the end.

**3:30 — Resume (45s).** Re-prompt the heal with the guardian's diagnosis → second heal targets the
right element → guardian verifies → **confidence 100/100, source confirmed** → the held card clears
(the hold is marked *superseded*, not rejected — the seller never declined it) and a normal proposal
appears. "Sharper heal, re-validated, and now it's a change the seller can trust. One click."

> Show the sharpened prompt itself, from the event log's *show the re-prompt* toggle. Vouch's
> validator writing Scraper Studio's next instruction is the most legible proof that we wrapped the
> heal loop rather than bolted onto it.

## Optional beat (if you have 45s spare, or for the Q&A)

Press **Bad heal: original price**. This is the same story with the volume turned down: the heal now
reads the *crossed-out* price instead of the sale price - only ~14% off, not 100x.

> "This is the one a distribution check cannot catch. Fourteen percent is a plausible price move, so
> nothing statistical fires. What catches it is an invariant: a sale price can never be higher than the
> price it is discounted from. And notice the harm flips - here we'd have priced *above* the market and
> lost the sale, not undercut ourselves. No floor rule helps you in that direction. Only checking the
> number does."

Worth having ready even if you cut it: it is the sharpest answer to "couldn't you just threshold on
price change?", and it shows the guardian is a battery of different kinds of evidence rather than one
statistic with a knob on it.

**4:15 — Close (30s).** "Scraper Studio heals the scraper. Vouch makes sure the heal didn't start
lying — inside a product where trusting the number is the whole job." Land on the criteria: *use of
Scraper Studio* (we wrap its heal loop), *reliability & self-healing* (that's the product),
*impact* (margin saved), *clean code* (the tiered validator is tested).

## Do / don't

- **Do** use real Scraper-Studio vocabulary in the event log ("heal proposed", "awaiting approval",
  "approved and committed"). It signals you understood the tool.
- **Do** show honest data state — a gap in the price chart for the held cycle, not a fake straight line.
- **Don't** show a "healing…" spinner as if it were the feature. The feature is the *held decision*.
- **Don't** over-scope the live demo. MOCK_MODE + technique A is the reliable spine; live site is a bonus.
