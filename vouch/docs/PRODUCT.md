# PRODUCT.md — Vouch

> Single source of truth for what Vouch **is**, who it's **for**, and what we're
> building for the hackathon. If a feature doesn't serve the story below, it's a
> roadmap slide, not a build.

## Positioning

**Vouch is the trust layer for automated decisions made on scraped data.**
It validates a self-heal *before* the number is allowed to trigger an action — so
silently-broken data never moves your business. (Bright Data Scraper Studio does
the self-healing; Vouch validates the proposed fix at the approval gate and, when
it fails, re-prompts a sharper one.) **Repricing is the first application, not the
product.**

The product is not the reprice. The product is the **verdict**.

## The primitive: the verdict

Every scraped datapoint produces one portable object. As shipped by `POST /verify`
(see [AS-IS.md](AS-IS.md) for the authoritative shape):

```
verdict = {
  decision:        pass | review | fail,   // pass→confirm, review→hold, fail→reject
  confirmed:       true | false,           // == (decision == pass)
  confidence:      0 – 100,
  brief:           "plain-English why we believe / doubt this number",
  failures:        [ { code, severity, field, message, evidence } ],
  judge_consulted: true | false
}
```

The repricing engine is just the **first consumer** of this verdict — and it
consumes it through the *same* boundary an outsider would (`verify_rows` behind
`POST /verify`), not a private path. Anything else — a different pricing pipeline,
an inventory system, an AI agent — can gate on the same call (with its own
schema via `orderings`/`field_descriptions`, and its own model key). That the
verdict is a real, callable, dogfooded primitive — not just a demo beat — is what
makes Vouch *infrastructure* rather than a tool.

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
2. **The verdict as a gate** — the verdict is consumable by something *other than*
   our own repricer: `POST /verify` (its own docs at `/trust/docs`), which any
   pipeline can call. This is no longer just a demo beat — the repricer itself
   goes through it, which is what actually earns the "infrastructure" claim.

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
