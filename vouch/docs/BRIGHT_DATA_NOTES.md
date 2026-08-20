# Bright Data Scraper Studio — operational notes

Everything here was confirmed against the docs or learned the hard way against the live API with
`@brightdata/cli` **v0.3.5**. Read it before touching the live path; several of these cost us real
credits or left junk on the account.

---

## The heal loop, and why Vouch can exist

```
brightdata scraper create <url> "<description>"     -> c_* collector id
brightdata scraper run    <collector_id> [url]      -> rows
brightdata scraper heal   <collector_id> "<prompt>" -> STOPS at the approval gate
brightdata scraper approve <collector_id> [--reject]
```

Behind them:

| CLI | API |
|---|---|
| `scraper create` | `POST /dca/collector` then `POST /dca/collectors/{id}/automate_template` |
| `scraper run` | `POST /dca/trigger_immediate` → `GET /dca/get_result` (or `/dca/crawl` with `--sync`) |
| `scraper heal` | `POST /dca/collectors/{id}/refactor_template` → poll `.../progress` |
| `scraper approve` | `POST /dca/collectors/{id}/resume_automation_job` `{"message": true｜false}` |

**The load-bearing fact:** without `--auto-approve`, `heal` exits `0` with a
`status: "awaiting_approval"` envelope containing **`preview_result`** — the sample rows the fixed
scraper *would* return. That is what the guardian validates. The whole product depends on it.

**Scraper Studio's own UI shows only the code diff** on Accept/Decline. `preview_result` is surfaced
by the CLI/API path alone, so Vouch validates data the approval screen cannot show a human.

**Never pass `--auto-approve`.** It commits without the gate.

---

## Traps we hit

### 1. `description` is capped at 500 characters

Undocumented in the docs pages; visible in `scraper create --help`. Over the limit you get:

```
Failed to start AI generation for collector c_xxx: Error: Invalid description
  Status: 400
```

**And the collector still exists.** `create` provisions the template *first*, then starts AI
generation, so a rejected description leaves a half-built orphan behind.
`brightdata.MAX_DESCRIPTION_CHARS` now validates this locally so the call never leaves the machine.

Shorter descriptions also tend to produce better scrapers — the AI does worse with a wall of caveats
than with one clear sentence per field.

### 2. `preview_result` is a SAMPLE, and the docs never say how big

Every example in Bright Data's docs elides the array with `…`, so the size is undocumented. Measured
against our live collector: **1 row, against a 96-row baseline.**

This matters more than it sounds. Any validation that reasons about volume will measure the preview
instead of the heal:

```
ROW_COUNT_SHIFT        Row count changed from 96 to 1.
CARDINALITY_COLLAPSE   'name' went from 96 distinct values to 1
```

Both are artefacts of the sample size. The heal in question had extracted a perfectly good price. So
`run_all_checks(..., is_sample=True)` stands those checks down, and `HealProposal.is_sample` carries
the distinction from the gate (always a sample) versus the mock fixture (a full-size stand-in).

Detection does not suffer, which is the part worth knowing — verified against the real 96-row baseline
with a one-row preview:

| One-row preview contains | Verdict |
|---|---|
| a legitimate price | PASS 100 |
| the shipping cost in `price` | FAIL 40 · `COLUMN_SWAP` |
| a null price | REVIEW 75 · `NULL_SPIKE` |
| no `price` field at all | FAIL 40 · `FIELD_MISSING` |
| a crossed-out original (14% high) | FAIL 40 · `VALUE_ORDER_INVERTED` |

Those four all work on a single row because none of them needs a distribution: three are row-local
facts, and `COLUMN_SWAP` asks which distribution a value sits *on*, not how it is spread. Only
`_profile_distance` needed adjusting — on one row `min == max == median`, so those terms carry no
information and actively distort the comparison; below `MIN_ROWS_FOR_DISTRIBUTION` it compares medians
only.

### 3. There is no way to delete or list collectors programmatically

No `scraper list`, no `scraper delete`. The CLI surface is exactly `create`, `run`, `heal`, `approve`.
So every failed `create` leaves an orphan you must remove by hand at
`https://brightdata.com/cp/scrapers`. Check that page after any failed run.

### 4. AI generation takes 5–10 minutes

The CLI's own examples say so. Two consequences:
- pass a generous `--timeout` (we default to 900s in `scripts/create_collector.py`);
- do not run it inside anything with a shorter wall-clock cap, or you lose the collector id from
  stdout while the job keeps running server-side — orphan number two, for us.

### 5. `--url` on `heal` is cosmetic

Docs: *"Verify target woven into the success `next_step` hint (not sent to heal call)."* The request
body is `{"prompt": ..., "custom_input": []}`. Harmless to pass; do not build logic on it.

### 6. Two different env var names for one credential

| Surface | Variable |
|---|---|
| CLI (`@brightdata/cli`) | `BRIGHTDATA_API_KEY` |
| Python SDK (`brightdata-sdk`) | `BRIGHTDATA_API_TOKEN` |

`config.py` carries both. `brightdata login` also works and stores credentials at
`%APPDATA%\brightdata-cli\credentials.json` on Windows.

### 7. The Python SDK cannot drive the heal loop

`brightdata-sdk` exposes only `run` / `trigger` / `status` on `scraper_studio`. No `heal`, no
`approve`, no `reject`. **The CLI is the only self-serve surface for the heal loop**, which is why
`scraper/brightdata.py` shells out via `npx` rather than importing an SDK. It is not a dependency.

### 8. `npx` is not executable by bare name on Windows

It is a `.cmd` shim, so `subprocess.run(["npx", ...])` raises `FileNotFoundError` even with Node
installed. `brightdata._npx()` resolves it with `shutil.which` instead — deliberately not `shell=True`,
which would put a heal prompt through shell quoting.

### 9. AI-Flow caps concurrent jobs at 3

A 4th concurrent `create`/`heal` returns `429 Cannot run more than N jobs in parallel`. The CLI retries
with exponential backoff (`--max-retries`, default 4). **`service.run_all_cycles` is deliberately
serial** — fanning out across SKUs would spend the demo in backoff.

### 10. After `scraper approve`, the collector is temporarily disabled

Immediately after a heal is approved, both `scraper run` (CLI) and `POST /dca/trigger` (REST) return:

```
HTTP 403 {"error":"Collector disabled"}
```

This is a Bright Data platform state, not a Vouch error. The collector must be **re-enabled from the
control panel** at `https://brightdata.com/cp/scrapers/<id>` before it can run again. There is no
programmatic enable/disable surface in the CLI — check the dashboard after every approved heal.

---

## Cost

- Scraper Studio bills **1 credit per page load**, against **5,000/month** free.
- Hackathon participants get **$50** more via the `wemakedevs` promo code — lowercase, entered in the
  billing section of the Bright Data profile. Signing up alone does not grant it.
- A failed `create` still costs the AI generation attempt. Validate locally first.

---

## Target: Newegg

`https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96`

All verified by direct fetch:

- **Server-rendered.** A plain `curl` with no User-Agent returns ~1.2 MB with names, prices,
  was-prices, shipping, ratings and stock in the initial HTML. **Browser mode is not needed.**
- `PageSize=96` yields **88 tiles in one request**. (`36` → 33, `60` → 54.)
- Behind **Cloudflare**, but six rapid sequential page fetches all returned 200 with no challenge.
  Softest of the targets we evaluated — Amazon 503s immediately, Shein benchmarks at ~22% success.
- **`Desktop-Graphics-Cards/SubCategory/ID-48` 301s** to the `GPUs-Video-Graphics-Cards` spelling. Use
  the canonical one so the collector does not burn a redirect hop.
- **robots.txt permits** `/GPUs-Video-Graphics-Cards/` and `/p/pl`; no `Crawl-delay`.
  ⚠️ It *fully* blocks three user agents: **`ChangeDetection`**, `008`, `Nutch`. Do not let a
  price-tracking tool identify itself as `ChangeDetection`.
- **No pre-built Bright Data Newegg scraper exists** — Newegg is absent from both the scraper library
  and the dataset marketplace (only legacy lead-gen landing pages and a $2k/mo managed service). So a
  custom Scraper Studio collector is genuinely non-redundant here, unlike Amazon.

### Page quirks the collector has to survive

| Quirk | Why it matters |
|---|---|
| The price is **split across elements** — `<strong>1,119</strong><sup>.99</sup>` | A naive `strong` selector yields `1119`, losing the cents |
| `<li class="price-was">` is emitted on **every** tile but is usually **empty**; only the inner `.price-was-data` is conditional | Selecting the outer element gives 36 hits and 24 blanks. Real coverage is ~**33%** |
| Savings render as `5%` on category tiles but `$560.00 (16%)` elsewhere | Same logical field, two shapes |
| `More options from $1,339.99 - $2,499.00` | A range across variants, **not** this SKU's price |

The ~33% `original_price` coverage is fine for `check_value_ordering`: it compares only rows where both
sides are present, and a swap inverts 100% of those.

### Two things to assert
- **Pin `www.newegg.com`.** `newegg.ca` does not redirect to `.com` and serves a different catalogue at
  different prices (first tiles `$699 / $1,029 / $1,669` vs `.com`'s `$519.99 / $469.99 / $1,087.99`).
- **Assert `"currency":"USD"`** from the page's JSON-LD, so a proxy-region change can never silently
  poison price history with CAD.

### Terms of use — disclose it
Newegg's Terms (updated 2026-07-21) prohibit accessing the site *"through any automated means,
including but not limited to the use of scripts or web crawlers"*, while robots.txt permits the exact
paths we use. That contradiction is standard across major retail — Amazon's posture is identical, and
Bright Data sells Amazon/Walmart/eBay datasets regardless. It is a policy consideration, not a
technical one. We keep volume to a single request per cycle, never authenticate, and do not
redistribute the data.
