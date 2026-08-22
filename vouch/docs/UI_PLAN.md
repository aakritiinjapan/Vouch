# UI_PLAN.md — Vouch console & site

> The build reference for the UI. Wireframes + the rules behind them.
> Companion docs: **[PRODUCT.md](PRODUCT.md)** (what we sell), **[AS-IS.md](AS-IS.md)**
> (what's actually built). This file is where product intent becomes screens.

## North star

The whole UI serves the locked positioning: **Vouch is the trust layer for
scraped data; the verdict is the product; repricing is its first application.**

- **The console answers one decision:** *"Do I trust this competitor price enough
  to let it move my listing — yes / no / not yet?"*
- **Hero narrative = trust infrastructure, proven by one visceral commodity case.**
- **Optimize for judges via one sharp story.** Depth of one story over breadth.
- Scope the demo to **one competitor (Newegg)** and the commodity-SKU wedge.

## Visual system — "Verdict" (unified dark, editorial, type-led)

The whole product is **one continuous dark surface** across hero, console, and
Trust API — no light/dark split. Hierarchy comes from **elevation, light, and
space**, not boxes. Personality is carried by **typography and structure**;
colour stays disciplined (state colours mean things, they never decorate).

**Palette**
| Role | Hex | Use |
|---|---|---|
| Canvas | `#0B0A10` | deep ink w/ a whisper of violet, faint grain + one soft glow behind hero — never flat black |
| Surface / raised | `#151420` → `#1B1A26` | the few main regions; low soft shadow + `rgba(255,255,255,.07)` hairline |
| Ink | `#F4F2EC` / `#A6A4B0` / `#6B6978` | primary (warm off-white) / secondary / muted |
| Verified (PASS) | `#4ADE9E` | state only |
| Held (FAIL) | `#FF5C5C` | state only — clean coral-red, not orange |
| Watch (review) | `#F2C14E` | state only, sparing |
| Brand / interactive | `#8B7CFF` | links, focus, primary action (distinct from state) |
| Signature gradient | violet→mint aurora | ONE place only: the gauge sweep + hero atmosphere |

**Type** — Bricolage Grotesque (display/editorial voice) · Inter (body/UI) ·
JetBrains Mono (data/verdict/gauge numerals). Exact scale: hero
`clamp(2.75→4.5rem)/800/-0.03em/lh.98`; page title `2.5rem/700`; H2 `1.375rem/600`;
lead `1.125rem/400`; body `15px/lh1.55`; eyebrow `11px mono uppercase +0.16em`.
Big display↔body contrast = editorial drama.

**Boxes** — console is **5 regions max**, separated by space + faint elevation +
hairlines, not nested bordered cards: ① header (identity·scope·demo) ② trust
metrics ③ the decision (held — hero) ④ ready to apply ⑤ receipts (right rail,
divider not box). One radius, one shadow, 8px rhythm.

**Motion** — a considered hero page-load reveal; the gauge arc draws to value on a
verdict; hover micro-interactions. `prefers-reduced-motion` fully respected.

## The through-line: one Verdict object, everywhere

The single most important UI decision. The guardian's verdict renders as **the
same object on every surface** — the held card, the live receipts, and the Trust
API. Seeing the identical object in all three places is what makes "the verdict
is the product, plug it into anything" *shown* rather than claimed.

**Signature — the Precision Verdict Gauge.** A mathematically-exact arc meter:
hairline track, an accent arc drawn to the 0–100 score, precise ticks at the
60/85 thresholds, tabular-mono score + PASS/FAIL glyph, coloured by state. Crisp
round-capped SVG, subtle draw-in; simplifies (never clutters) at small sizes.
Precision instead of ornament. Reused at three sizes (hero / held card /
receipts+inline) with identical geometry.

```
          ·  ·  ·                      the gauge, schematically:
       ·           ·                   - track: hairline ring
     ·     ┌─────┐   ·                 - arc: state colour, 0→score
     ·     │ 40  │   ·  ← score (mono) - ticks: at 60 and 85
     ·     │FAIL │   ·                 - center: score + PASS/FAIL
       ·   └─────┘ ·
          ·  ·  ·
```

`view as API →` is the **bridge**: it links a held decision straight to the Trust
API pre-loaded with that row, turning the infra reframe (demo Act 2) into a click.

Trust-score legend (a small `ⓘ` popover, so the number means something):

```
High  ≥ 85   safe to apply automatically
Med   60–84  worth a human glance
Low   < 60   very likely wrong — rejected
```

## Surfaces (three, one nav, shared identity)

`Console` · `Trust API` in the nav. Same top-right tenant identity everywhere so a
viewer always knows where they are. (Setup is **not** in the build — see Scope.)

### A. Hero (`/`)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  ◆ VOUCH                        How it works   Trust API      [ Launch console ] │
├───────────────────────────────────────────────────────────────────────────────┤
│     THE TRUST LAYER FOR SCRAPED DATA                              ← kicker        │
│     Never act on a number you can't verify.                       ← headline      │
│                                                                                 │
│     Vouch returns a verdict on every scrape — validated and self-healed          │
│     before anything acts on it. Its first job: making sure a broken              │
│     competitor scrape never moves your price.                     ← subhead       │
│                                                                                 │
│     [  See it catch a bad price →  ]      How it works ↓                          │
│                                                                                 │
│   ┌──────────── The competitor page changed. Your scraper "self-healed" ──────┐ │
│   │  … and started reading the $19.99 SHIPPING cost as the product price.      │ │
│   │      WITHOUT VOUCH                    │        WITH VOUCH                   │ │
│   │   ✕ auto-reprices to $19.99           │   ✓ catches the bad data           │ │
│   │   ✕ −$179.99/unit, margin gone        │   ✓ holds price at $1,279.99       │ │
│   │   ✕ you find out from your P&L        │   ✓ nothing bad happens ✋          │ │
│   └────────────────────────────────────────────────────────────────────────────┘│
├───────────────────────────────────────────────────────────────────────────────┤
│  THE VERDICT IS THE PRODUCT                                                       │
│  Every scrape returns one portable verdict. The repricer is just its first        │
│  consumer — send rows, get back trust.                                            │
│      ╭ VERDICT · ✕ FAIL · 40/100 (Low) · view as API → ╮   [ Try the Trust API →]│
├───────────────────────────────────────────────────────────────────────────────┤
│  Powered by ◇ Bright Data self-healing scrapers · Anthropic guardian              │
│  Next: the same trust layer for branded catalogs (similar-but-not-identical goods)│  ← teaser
└───────────────────────────────────────────────────────────────────────────────┘
```

### B. Console (`/console`)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ ◆ VOUCH   ● Console  ○ Trust API                          Voltix Components ▾    │
│ Pricing desk — we move your price only on competitor data we can prove is real.  │
├───────────────────────────────────────────────────────────────────────────────┤
│ Checking against  ·  Newegg  ·  8 products                                        │
├───────────────────────────────────────────────────────────────────────────────┤
│ ▶ DEMO — simulate real scraping events                                    ⓘ     │
│  [ Check competitors now ]  [ Simulate: scraper breaks → self-heals ]            │
│  [ Simulate: shipping-price swap ]  [ ↻ Reset demo ]                             │
├───────────────────────────────────────────────────────────────────────────────┤
│ vs Newegg — 1 reprice on hold · 3 ready to apply · confirmed 2m ago               │
├───────────────────────────────────────────────────────────────────────────────┤
│ TODAY   ┌ Bad reprices caught 2 ┐ ┌ Margin protected $359.98 ┐ ┌ Sources 7✓·1⏸ ┐ │
│         └ blocked on bad data   ┘ └ margin bad data would cost┘ └ of 8 tracked  ┘ │
├──────────────────────────────────────────────────┬──────────────────────────────┤
│ NEEDS YOUR DECISION                                │ HOW VOUCH DECIDED (live)      │
│                                                    │ plain-English receipts        │
│ ⏸ ON HOLD — 1                                       │ ───────────────────────────  │
│ ┌───────────────────────────────────────────────┐ │ ● MSI RTX 5080 · vs Newegg    │
│ │ MSI RTX 5080 Gaming Trio  ·  vs Newegg           │ │   ← this card                 │
│ │  Our price         $1,279.99                    │ │  1 competitor price empty     │
│ │  Our margin        22%   (floor 10% ≈ $1,100)   │ │  2 scraper auto-fixed itself  │
│ │  Competitor price  ⚠ couldn't verify            │ │  3 guardian checked it →       │
│ │  ╭ VERDICT ─────────────────────────────────╮  │ │    ╭ ✕ FAIL · 40/100 (Low) ╮ │
│ │  │ ✕ FAIL · trust 40/100 (Low)              │  │ │    ╰ mixed up 2 columns    ╯ │
│ │  │ read SHIPPING ($19.99) as the price       │  │ │  4 re-asked → still wrong     │
│ │  │ view as API →                             │  │ │  5 price left unchanged ✋     │
│ │  ╰────────────────────────────────────────────╯  │ │ ───────────────────────────  │
│ │  If auto-applied: −$179.99/unit  [Show damage]  │ │ ○ RTX 4070 ✓ PASS → $549→$541 │
│ │  Trust: High≥85 · Med 60–84 · Low<60       ⓘ    │ │ ○ RX 7800  ✓ PASS → $499→$489 │
│ │  [ Investigate ]        [Approve anyway][Skip]  │ │                               │
│ └───────────────────────────────────────────────┘ │ (click a card ↔ its receipt)  │
│ ✓ READY TO APPLY — 3  (verdict: PASS)              │                               │
│ ┌───────────────────────────────────────────────┐ │                               │
│ │ [ Approve all 3 ]                               │ │                               │
│ │ RTX 4070  $549→$541  ✓ PASS 100  [Apply][Skip]  │ │                               │
│ │ RX 7800   $499→$489  ✓ PASS 100  [Apply][Skip]  │ │                               │
│ └───────────────────────────────────────────────┘ │                               │
└──────────────────────────────────────────────────┴──────────────────────────────┘
```

Held card order = **numbers → verdict on those numbers → consequence → actions**.
The Verdict chip is the pivot; the ready-list and receipts use the same PASS/FAIL
language, so every decision on screen reads as a verdict, not a reprice.

#### Held card → Investigate

```
┌─ Investigate ─────────────────────────────────────────────────────┐
│ The guardian's working                                             │
│   Field checked ............ price                                 │
│   Value it returned ........ $19.99                                │
│   Its normal price range ... ~$1,299.99  (last good run)          │
│   The shipping column's range ~$17.99                             │
│   → The "price" values line up with SHIPPING, not price.          │
│ What we told the scraper to fix (attempt 2 of 2)                   │
│  "…'price' was reading SHIPPING. Re-extract the item's own current │
│   sale price; leave shipping as its own field."                    │
│ Collector left unchanged — rejected before anything committed.     │
│                                        [ view this verdict as API →]│
└────────────────────────────────────────────────────────────────────┘
```

#### Held card → Show the damage

```
┌─ Show the damage ─────────────────────────────────────────────────┐
│ What acting on this would have done                               │
│   Our price   $1,279.99 → $1,100.00   (our floor rule caught it)   │
│   Our margin  22%       → 9%                                       │
│   Per unit    −$179.99 margin, every one sold                      │
│   No floor rule → $19.98 (margin −98%). A floor caps the disaster; │
│   only verifying the data prevents it.                             │
│   Price vs Newegg                                                  │
│   $1300 ●──●──●╌╌╌·  ← gap = the period we couldn't trust          │
│   $  20             ·                                              │
└────────────────────────────────────────────────────────────────────┘
```

### C. Trust API (`/trust-api`)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ ◆ VOUCH   ○ Console  ● Trust API                          Voltix Components ▾   │
│ For developers & platform teams — the guardian's verdict as a stateless API.     │
├───────────────────────────────────────────────────────────────────────────────┤
│ The verdict is the product. The repricer is one consumer — anything can be.       │
│ ↳ Verifying: MSI RTX 5080 (the row you clicked on the Console)                    │
├───────────────────────────────────────┬───────────────────────────────────────┤
│  TRY IT                                │  RESPONSE  ·  POST /verify   200 · 41ms │
│  Scenario  ● Column swap               │  {                                      │
│            ○ Clean heal                │    "decision": "fail",                  │
│            ○ Crossed-out (was) price   │    "confirmed": false,                  │
│  Sending: candidate 8 + baseline 8     │    "confidence": 40,                    │
│                            [edit ▾]    │    "brief": "…'price' matches the       │
│      [ Run through the guardian ]       │       distribution of 'shipping'…",     │
│   ╭ VERDICT ───────────────────────╮   │    "failures":[{"code":"COLUMN_SWAP",   │
│   │ ✕ FAIL · trust 40/100 (Low)     │   │      "severity":"critical", … }],       │
│   ╰──────────────────────────────────╯   │    "judge_consulted": false }           │
│   Same object the Console acted on.    │  curl -X POST $VOUCH/verify -d '…'       │
└───────────────────────────────────────┴───────────────────────────────────────┘
```

Backed by the real `POST /verify` endpoint (see AS-IS.md), so this is live, not a
mockup. The scenario picker drives deterministic sample data for the demo.

## Build scope vs. roadmap

**Build for the hackathon:**
- Hero (contrast proof + verdict-is-product band + teaser)
- Console: identity/purpose header, `vs Newegg` scope, DEMO strip, trust metrics,
  held card (with Verdict chip + `view as API` bridge), Investigate, Show the
  damage, ready-to-apply list, live receipts
- Trust API (wired to `POST /verify`)
- The Verdict chip component, reused across all three

**Roadmap only — wireframe/slide, do NOT build:**
- Setup page (products/prices/competitor CRUD, pin competitor URL)
- Multi-competitor scope, filters, "N competitors tracked"
- Branded-similar catalogs

Rationale: these are real-user/robustness breadth, deliberately traded away for
"one sharp story." Building them dilutes the infra narrative and creates honesty
gaps (e.g. "3 competitors" with no data). Keep the demo `vs Newegg`, full stop.

## Demo arc → surface mapping

1. **Disaster prevented (visceral):** Console — trigger the break, watch the held
   card + counterfactual. Uses `DEMO_DATASET=sample_runs` for both failure types.
2. **The reframe (infrastructure):** click `view as API →` on the held card →
   Trust API shows the *same* verdict as a portable object.
3. **The reach (teaser):** hero's branded-catalog line + "any scraped-data pipeline."

## Design principles applied

- **5-second rule** — a new viewer learns where they are, what matters, what to do,
  without domain jargon. Every metric/label defines itself inline.
- **Plain language over machine tags** — `COLUMN_SWAP` → "mixed up two columns
  (read shipping as the price)"; `40/100` always carries a High/Med/Low label.
- **Familiar data first** — the held card leads with Our price / Our margin /
  Competitor status before the impact number.
- **Progressive disclosure** — evidence, re-prompt, and chart live behind
  Investigate / Show the damage, not on the collapsed card.
- **Restructure before refresh** — get structure + copy right (this doc), then a
  visual pass (run the `frontend-design` skill).

## Placeholders to confirm before build

- Tenant name `Voltix Components` (stand-in for the demo seller).
- Competitor `Newegg` (matches the real fixture dataset).
- Exact trust-metric wording.
