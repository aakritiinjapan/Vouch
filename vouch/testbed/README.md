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

Then heal against the broken page and let the guardian judge the preview:

```bash
cd ../backend
MOCK_MODE=false python -m scripts.live_heal --collector c_YOUR_ID --prompt-style vague
```

---

## Verify before you deploy

```bash
python verify.py            # runs the REAL guardian over all 8 variants, offline, free
python verify.py --verbose  # also prints each brief
```

`verify.py` renders each variant, **parses the HTML back out the way a collector would**, and runs
`run_all_checks` + `decide` against the clean page's baseline. Parsing rather than reusing the
generator's dicts is the point: a field that is unanchored in the markup shows up here as a failure
rather than as a surprise on live infrastructure. It caught three real design bugs when first run.

It asserts only that each variant trips its intended **check** — not the decision. Whether a fired
check crosses the hold threshold is `verdict.decide`'s scoring policy, and a testbed that encoded
policy would break every time a threshold was tuned, for a reason having nothing to do with the page.

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

Every product, price, rating and stock state on this page is **invented**. It is a test fixture, not
a storefront, and it says so in the footer, in an HTML comment, and via `robots: noindex, nofollow`.
Nothing here is for sale and no real retailer's data is reproduced.
