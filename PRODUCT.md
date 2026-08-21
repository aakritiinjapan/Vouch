# PRODUCT.md — Vouch

> Single source of truth for what Vouch **is**, who it's **for**, and what we're
> building for the hackathon. If a feature doesn't serve the story below, it's a
> roadmap slide, not a build.

## Positioning

**Vouch is the trust layer for automated decisions made on scraped data.**
It validates and self-heals a scrape *before* the number is allowed to trigger an
action — so silently-broken data never moves your business. **Repricing is the
first application, not the product.**

The product is not the reprice. The product is the **verdict**.

## The primitive: the verdict

Every scraped datapoint produces one portable object:

```
verdict = {
  status:         confirmed | held | rejected,
  confidence:     0.0 – 1.0,
  evidence:       [ why we believe / doubt this number ],
  counterfactual: "if you had trusted this, you would have done X and lost $Y"
}
```

The repricing engine is just the **first consumer** of this verdict. Anything
else — a different pricing pipeline, an inventory system, an AI agent — could
consume the same verdict through a gate/webhook/API. Framing the verdict as the
primitive is what makes Vouch *infrastructure* rather than a tool.

## ICP (who v1 is for)

**Commodity-SKU sellers** — the *same* product sold by *many* vendors (GPUs,
racquets, components). Price is the only variable, so a silently-broken scrape is
catastrophic. This is the hero. Branded-similar catalogs (Shopify-style,
similar-but-not-identical goods) are **roadmap**, not build.

## The one decision (UI north star)

The console exists to answer exactly **one** question:

> **"Do I trust this price enough to let it move my listing — yes / no / not yet (held)?"**

Everything on screen is either evidence for that verdict or it is cut. The UI
struggled because it was three screens (dashboard + approval queue + scraper
health) pretending to be one. Fix the decision, and the screen resolves.

## Two surfaces

1. **The console** — the one-decision screen above.
2. **The verdict as a gate** — show that the verdict is consumable by something
   *other than* our own repricer (an API response / webhook / "plug into your
   pipeline"). This is the 30 seconds that earns the "infrastructure" claim.

## Demo arc (~3 min, judge-facing)

1. **The disaster, prevented.** Competitor changes their page → scrape silently
   breaks → Vouch catches it, refuses the reprice, self-heals the scraper,
   re-validates. Land the **counterfactual**: "if you'd trusted that, you'd have
   dropped price to $X and lost $Y margin." (Visceral proof.)
2. **The reframe.** "That verdict is the product. Here it is as an API a repricer
   consumed — but anything could." Show the gate.
3. **The reach.** Branded-similar teaser + "same trust layer, any scraped-data
   pipeline."

## Scope

**In scope (build):**
- Core guard loop (untouched — it's the moat)
- One-decision console
- Manual "pin this competitor URL"
- Verdict-as-a-gate surface (API/webhook demonstration)
- Quantified counterfactual
- Branded-similar teaser (slide only)

**Out of scope (roadmap slide only):**
- Auto-find competitor
- Multi-category / catalog scale
- Branded-similarity scoring engine

## Decisions locked

- Optimize for: **judges, via one sharp story** (dev time is not our constraint —
  decisiveness and demo narrative are).
- Hero narrative: **trust infrastructure**, *proven by* one visceral commodity
  case.
- Scope wedge: **commodity hero + branded teaser.**
