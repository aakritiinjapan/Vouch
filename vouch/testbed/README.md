# Voltmart — the testbed storefront

A fake shop we control, so a heal can be broken **on purpose** and the guardian's verdict earned
against real Bright Data infrastructure instead of a mutated fixture.

Everything else in this repo validates against `tests/fixtures/*.json` — real Newegg rows corrupted
in Python. That proves the checks work on the data. It does not prove the *loop* works: a real
collector, reading a page that really broke, stopping at a real approval gate. This page closes that
gap, and it costs one collector.

---

## Why a purpose-built page and not a real shop

The live Newegg category page cannot exercise the product's own headline failure:

| | Newegg (live) | Voltmart |
|---|---|---|
| `shipping` | **"Free Shipping" on 90 of 92 tiles** — no distribution to swap onto | $4.99–$24.99, varying on every row |
| `original_price` | collector returns it **100% null** | present on 22 of 30 rows, 5–30% above price |
| breakable | no — someone else's page | yes — regenerate and redeploy |

The three numeric fields are also deliberately far apart — price ~$565, shipping ~$15, rating ~4.2 —
because `check_column_swap` refuses to claim a swap between fields that were not distinguishable at
baseline. And `original_price` sits only 5–30% above `price`, which is *inside* that same blind spot,
so `check_value_ordering` gets a real target on the same page. Both checks, one fixture.

---

## Deploy

The page is a single self-contained `index.html` — no build, no JS, no dependencies. Server-rendered,
so Scraper Studio needs no browser mode and a run is one page load.

```bash
cd vouch/testbed
python generate.py                       # writes index.html (clean baseline)
python generate.py --adversarial         # ...and p1/p2/p3.html, the page-structure probes
```

Then either:

- **Netlify drop** — drag this folder onto <https://app.netlify.com/drop>. Fastest.
- **Netlify CLI** — `npx netlify-cli deploy --dir . --prod`
- **Any static host** — it is one file.

`netlify.toml` is included so `/` serves the page directly.

---

## Create the collector

Paste this as the description. It is **369 characters**, inside the CLI's undocumented 500-char cap:

```
Extract every product tile on this graphics-card listing page. For each tile: name (the product
title link), price (the large current price), original_price (the smaller crossed-out price, null
when absent), shipping (the dollar amount on the Shipping line), rating (the number before "out of
5"), in_stock (true when the badge reads In Stock, false when Out of Stock).
```

```bash
cd vouch/backend
MOCK_MODE=false python -m scripts.create_collector \
    --url https://YOUR-SITE.netlify.app/ \
    --description "...the text above..."
```

AI generation takes 5–10 minutes. Expect 30 rows.

---

## Break it

```bash
python generate.py --list                # every variant and the check it should trip
python generate.py --variant swap        # rewrite index.html as the broken page
npx netlify-cli deploy --dir . --prod    # redeploy
```

| Variant | The edit | Should trip | Verdict today |
|---|---|---|---|
| `clean` | — | — | PASS 100/100 |
| `swap` | price ↔ shipping | `COLUMN_SWAP` 🔴 | FAIL 40/100 |
| `inverted` | price ↔ original_price | `VALUE_ORDER_INVERTED` 🔴 | FAIL 40/100 |
| `missing` | shipping column removed | `FIELD_MISSING` 🔴 | FAIL 40/100 |
| `drift` | price and original_price ×4 | `NUMERIC_DRIFT` 🟠 | FAIL 50/100 |
| `nulls` | price blanked on 70% of rows | `NULL_SPIKE` 🟠 | REVIEW 75/100 |
| `collapse` | every name pinned to one string | `CARDINALITY_COLLAPSE` 🟡 | PASS 90/100 ⚠️ |
| `instock` | in_stock forced false | `BOOL_RATIO_SHIFT` 🟡 | PASS 90/100 ⚠️ |
| `fake_sale` | real 30% cut, was-price inflated 1.6× | `REFERENCE_PRICE_UNSUPPORTED` | PASS 97/100 ✅ |

### `fake_sale` — the second application

Every price genuinely drops 30%, so a shopper sees a real reduction. But the crossed-out number it's
measured from is 1.6× anything the page ever charged. Nothing on the page is internally inconsistent:
`price` is still below `original_price`, so the ordering invariant is satisfied, and both medians move
together so nothing drifts. **Only a dated record of what the page said before the sale can catch it**
— which is why this is a scraping problem and not an arithmetic one.

`PASS 97/100` is the *correct* outcome, not a gap. Our extraction is right — we read the page exactly
as written — so the heal is sound and must commit. The finding is about the retailer's claim, and
`check_reference_price` is scored LOW precisely so it can never reject a good repair for something the
repair didn't cause.

The pre-sale record is supplied by the caller (`reference_prices={name: price}`). In production it
comes from the confirmed `CompetitorObservation` rows; in `verify.py` it comes from the clean page.
Omit it and the check stands down entirely — an ordinary heal has no sale to audit.

Then heal against the broken page and let the guardian judge the preview:

```bash
cd ../backend
MOCK_MODE=false python -m scripts.live_heal --collector c_YOUR_ID --prompt-style vague
```

---

## The adversarial pages — probing the healer, not the guardian

Everything above corrupts the **data** and leaves the markup alone. That tests the guardian: we
already know what went wrong and we are asking whether the checks say so. It tests the **healer**
not at all, because the healer was never given a structural decision to make.

These three vary the DOM instead. Each is a hypothesis about how Bright Data's AI picks a selector,
arranged so a wrong pick shows up in the extracted **values** — we cannot read the selector it
emits, so the page has to make the difference measurable.

```bash
python generate.py --adversarial          # writes p1.html, p2.html, p3.html
npx netlify-cli deploy --dir . --prod     # all three live at once
```

Give each page **its own collector**. A heal is a 5–10 minute AI job and AI-Flow caps concurrency at
3, so three collectors probed in parallel is an hour and one URL probed serially is a day.

| | Page | The DOM edit | Hypothesis | Severity |
|---|---|---|---|---|
| **P1** | `p1.html` | tile 1 has no crossed-out price and no delivery line; on tiles 2–30 the price and the delivery charge have traded places in the markup | the approval gate previews **one row**, so a selector fitted to tile 1 previews clean and is wrong on 29 of 30 | high |
| **P2** | `p2.html` | `price` and `shipping` in byte-identical markup — same class, same `$NN.NN`, adjacent siblings, no label — with shipping first | the healer anchors on **position**, not meaning | medium |
| **P3** | `p3.html` | visually and semantically identical, every class renamed, values untouched | the healer works from a DOM **cached at collector-creation time**, so it proposes selectors for classes that no longer exist | **highest** |

### P1 is the load-bearing one

The break is that the price and the delivery charge swapped places in the markup. The word
"Shipping" travelled with the delivery amount; the CSS classes did not. So `.price-current` reads
`$19.99 Shipping` in 21px bold and the small green `.price-ship` line holds the real price — a
textbook `COLUMN_SWAP`, and a heal is plainly warranted.

Tile 1 has no delivery line at all, so it had nothing to trade places *with*, and its
`.price-current` still holds the real price. That one difference splits the two anchors a healer can
reach for — both of which fit tile 1 perfectly:

| Anchor | Tile 1 | Tiles 2–30 |
|---|---|---|
| positional — first money node under `.item-price` | $1,999.99 ✅ | $19.99 — the delivery charge ❌ |
| semantic — the money *not* labelled "Shipping" | $1,999.99 ✅ | $1,149.99 ✅ |

The sharpest form of it: the positional reading reproduces the **incumbent** selector's output
exactly. The "repair" would change nothing at all and still look like a fix, because the only row
anyone is shown is the one row the incumbent already gets right.

### P3 is a two-step, and the order matters

```bash
python generate.py --adversarial                              # p3.html = the ORIGINAL layout
# ...create the collector against p3.html, confirm 30 good rows...
python generate.py --variant renamed_dom_after --out p3.html  # same page, every class renamed
npx netlify-cli deploy --dir . --prod                         # SAME url
```

The rename has to land on a URL the collector already knows, or there is no cached snapshot to be
stale. `netlify.toml` sends `Cache-Control: no-store` for exactly this reason — a cached response
would make a stale CDN indistinguishable from a stale DOM, which is the hypothesis under test.
Before healing, `curl` the URL and confirm you get `prod-card` and not `item`.

### Every one of them is winnable

For all three, a selector that is correct on **all thirty tiles** exists, and it is the one the
collector description already asks for. `verify.py` proves that offline: it reads each page twice,
once the lazy way and once the way the description asks, and asserts the second reading recovers the
clean page's values exactly. If the healer gets it wrong, the page answered the question and the
healer did not.

---

## Verify before you deploy

```bash
python verify.py            # the REAL guardian over all 9 variants + the 3 adversarial pages, free
python verify.py --verbose  # also prints each brief and each claim's evidence
```

`verify.py` renders each variant, **parses the HTML back out the way a collector would**, and runs
`run_all_checks` + `decide` against the clean page's baseline. Parsing rather than reusing the
generator's dicts is the point: a field that is unanchored in the markup shows up here as a failure
rather than as a surprise on live infrastructure. It caught three real design bugs when first run.

It asserts only that each variant trips its intended **check** — not the decision. Whether a fired
check crosses the hold threshold is `verdict.decide`'s scoring policy, and a testbed that encoded
policy would break every time a threshold was tuned, for a reason having nothing to do with the page.

The adversarial section asserts something different, because those pages make claims about Bright
Data rather than about the guardian. All it can settle offline is whether the **page** is shaped the
way the claim needs — that a right answer was reachable and a specific wrong answer was reachable
too. That matters more than it sounds: a malformed or unwinnable fixture is a far cheaper
explanation for a failed heal than a bug in the healer, and it is the explanation a sceptical reader
reaches for first.

### ⚠️ The two marked PASS above are worth knowing about

`CARDINALITY_COLLAPSE` and `BOOL_RATIO_SHIFT` are both MEDIUM, which costs 10 points. `decide()`
returns PASS at anything ≥85 with no critical or high finding — so **a lone medium finding can never
move the verdict off PASS.** The brief says *"'name' may now be pinned to a static element"* while
the decision says *safe to commit*.

Three of the eight checks (`CARDINALITY_COLLAPSE`, `ROW_COUNT_SHIFT`, `BOOL_RATIO_SHIFT`) can only
ever change an outcome in combination with something else. That may well be the right conservative
call — holding a price change over one medium signal is its own kind of failure — but it is a
deliberate policy choice, not an accident, and it is better stated than discovered by a judge.

---

## Honesty

Every product, price, rating and stock state on every page here is **invented**. They are test
fixtures, not a storefront, and each one says so in the footer, in an HTML comment, and via
`robots: noindex, nofollow`. Nothing here is for sale and no real retailer's data is reproduced.
