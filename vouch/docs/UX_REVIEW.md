# First-glance review of the console

Written after looking at the running app cold, as a judge would: thirty seconds, no context. The
verdict is that the screen is **clearer than it looks**, and what makes it feel complicated is one
structural decision rather than the styling. Nothing below is a criticism of the visual design, which
is good — it is about how many things the layout claims are happening.

## What lands immediately

- The tagline. *"Repricing that never acts on a number it can't verify"* states the product in nine
  words.
- The provenance line naming the real collector. That is the single most credible thing on screen and
  it is in the right place.
- That something is wrong, and that money is involved.
- The empty states. *"Every confirmed source is already priced where Vouch would put it"* explains a
  non-obvious behaviour (no-op suppression) without a tooltip.

## What does not land

### 1. One problem is presented as nine

This is the root cause of the "complicated" feeling. Queried from the API on a held cycle:

```
distinct collectors : 1
distinct check codes: 1
distinct briefs     : 1
```

All the seeded SKUs read the **same** competitor page, so they share **one** collector. A layout
change is therefore **one event** — but the screen showed 3 held cards plus 6 heal-log entries, each
repeating the same sentence. Nine renders of one finding.

A first-time viewer cannot tell whether they are looking at one problem or three, and the honest
answer — one bad fix, three affected SKUs — is more reassuring than what the layout implies.

*Partly addressed:* the backend now heals once per collector rather than once per product, which cut
the log from 6 events / 24 lines to **2 events / 8 lines**. The three held cards remain, because that
is a frontend grouping decision.

### 2. There is no way to fix anything from the thing that is broken

The card's four actions are *Investigate*, *Show the damage*, *Approve anyway*, *Skip this cycle*.
None of them fixes the problem. The actual remedy — **Re-prompt & resume** — is a header button,
spatially disconnected from the card it resolves.

So the card states a problem and offers no path out of it. For a product whose entire pitch is
"we caught this before it cost you money", the natural next question is *"so fix it"*, and that
sentence is not on the card.

**Suggestion:** promote re-prompting to the card's primary action. It is the only one that changes
the situation rather than accepting or deferring it.

### 3. Four numbers compete to be the headline

`$2,213` (KPI) · `−$951.00` (card hero) · `40/100` (meter) · `20.1%` (average margin).

The first two are the *same quantity* at different aggregations, which is worse than redundant — a
viewer who reads both assumes they measure different things. Pick one altitude for the money figure.

### 4. "MARGIN PROTECTED" is green next to a red alarm, and overclaims

Nothing has been protected yet — the reprice is *held*, awaiting a decision. The honest label is
exposure **avoided so far**, or simply *at risk*. As written, the most reassuring word on the screen
sits directly beneath the most alarming one.

### 5. The operator log carries the same weight as the decision queue

`README` §7 says the heal log is a **secondary** panel. On screen it is a full column of equal
prominence, and on a projector it competes with the held card for attention. A collapsed strip that
expands would say the same thing without the cost.

### 6. Minor: two numbers on the evidence panel look contradictory

The lead sentence says *"The healed price (**$19.99**)"* while the table below reads
`median in the proposed rows → **$0.00**`. Both are correct — $19.99 is that row's observed price,
$0.00 is the median across all 96 rows, because Newegg shipping is usually free — but they sit
adjacent with no cue that they are different statistics. Label the median "across all rows", or quote
the same statistic in both places.

## What I would change, in order of value

1. **Group the held cards into one incident** with a compact list of affected SKUs. One problem, one
   number, one set of actions. This is truthful, not just tidier: they share a collector.
2. **Move "Re-prompt the scraper" onto the card** as the primary action.
3. **Drop one money figure.** Keep the per-incident total or the per-SKU worst case, not both.
4. **Relabel `MARGIN PROTECTED`** to something that is true while the decision is still open.
5. **Collapse the heal log** to a strip by default.

A sketch of (1) and (2):

```
+----------------------------------------------------------------------+
|  !  One bad fix, caught before it moved any price                    |
|                                                                      |
|     Newegg changed their layout. Scraper Studio's fix started         |
|     reading the SHIPPING cost as the item price -- $19.99 instead     |
|     of ~$4,800.                                                      |
|                                                                      |
|     3 SKUs price against this source, so all 3 are on hold.           |
|     Had we trusted it:   -$2,213 per unit                            |
|                                                                      |
|       ZOTAC ARCTICSTORM RTX 5090     -$951.00                        |
|       MSI Gaming RTX 5090            -$653.40                        |
|       ASUS ROG Astral RTX 5090       -$609.00                        |
|                                                                      |
|     [ Re-prompt the scraper ]   show evidence . override . skip      |
+----------------------------------------------------------------------+
```

## What to keep exactly as it is

- **The evidence panel.** *"THE GUARDIAN'S WORKING"* with human labels beside the machine keys, and
  the re-prompt quoted verbatim under *"Written by the validator, not by a person"* — that is the most
  persuasive artefact in the build. It answers "did you actually do this, or is it a mock?" before
  anyone asks.
- **The provenance line** naming the live collector.
- **The `COLUMN_SWAP` badge.** Jargon, but the right kind: it signals the check is a real named thing
  rather than a vibe.
- **The honest empty states and the chart gap.**
