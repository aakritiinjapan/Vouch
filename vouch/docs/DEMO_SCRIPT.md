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
- **C — Underspecified-first-prompt.** Create the collector with a slightly ambiguous description so
  it grabs the wrong number, then heal with a sharper prompt. Same mechanism, zero mirroring, uses
  the live site throughout. Weakest as a "redesign" story but the most literally-what-happened.

> Fastest to build and rehearse: **A**, run entirely in `MOCK_MODE` with `propose_heal(..., _simulate="healed_swapped")`. The mock produces the exact swap deterministically, so the demo never depends on the network. Wire the real path (B or C) too if time allows, for a "and here it is against a live site" moment.

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
    Confidence: 22 / 100   ·   source: newegg-mirror (unconfirmed)   ·   check: COLUMN_SWAP
    [ Investigate ]   [ Approve anyway ]   [ Skip this cycle ]
```

"The heal *worked* — right rows, right format. But it silently swapped price and shipping. A normal
repricer would now match a $20 competitor and destroy the margin. Vouch caught it and **held the
change** — because we never reprice off a number we can't verify."

**2:45 — The counterfactual (45s).** Toggle a "what if we'd auto-approved" view: the price line
craters to $20, margin goes red. "This is the failure Vouch exists to prevent."

**3:30 — Resume (45s).** Re-prompt the heal with the guardian's diagnosis → second heal targets the
right element → guardian verifies → **confidence 96/100, source confirmed** → the held card clears
and a normal proposal appears. "Sharper heal, re-validated, and now it's a change the seller can
trust. One click."

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
