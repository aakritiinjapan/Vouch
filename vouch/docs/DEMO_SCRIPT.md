# Demo script (3 minutes)

Three minutes, not five. Judges watch a lot of these, and the arc lands harder tight.

The arc follows the product: **the verdict is the product; the repricer is where it obviously
matters.** So we open on the verdict idea, immediately prove the data underneath it is real, show
the guardian catch a silent lie, and then reveal the verdict as a standalone thing anything can
call. See [PRODUCT.md](../../PRODUCT.md) for positioning and [AS-IS.md](../../AS-IS.md) for what is
actually built (so no claim here outruns the code).

Two windows: a terminal with real CLI output (captured in advance — see
[`LIVE_CAPTURE.md`](LIVE_CAPTURE.md)) and the app at `http://127.0.0.1:5173` (Hero → Console →
Trust API views).

> UI element names below track [UI_PLAN.md](../../UI_PLAN.md). Give the script one final pass once
> the redesign lands, in case a label moved.

---

## The arc

> The verdict is the product → the collector under it is real → a real heal stops at the approval
> gate → the guardian catches a heal that would reprice a $6,900 card to $19.99 → the same verdict,
> live, as an API anything can call.

---

## 0:00 — The verdict, framed (15s)

Open on the **Hero**. Headline on screen: *"Never act on a number you can't verify."*

> "Self-healing scrapers fix themselves when a site changes — and sometimes fix themselves into
> reading the wrong number, silently. Vouch returns a verdict on every scrape before anything acts
> on it. Its first job: making sure a broken competitor scrape never moves your price."

Don't linger. The hero states the thesis; the terminal proves it.

## 0:15 — The collector is real (25s)

Cut to the terminal. Real `scraper run` output scrolling — 96 graphics cards, names, prices,
shipping, stock.

> "Ninety-six cards off Newegg's public category page, one request — a DataVerse Scraper Studio collector we
> built."

## 0:40 — The heal stops at the gate (30s) — the most important beat

Still in the terminal. Real `scraper heal`. It pauses at `awaiting_approval` and hands back
`preview_result`.

> "When a page changes, Scraper Studio heals itself. Without `--auto-approve` it stops *here* and
> hands back `preview_result` — the rows the fix *would* produce. Its own approval screen shows you a
> code diff; the CLI gives you the data. That gap is where this whole product lives."

Nobody else in this hackathon will have found this. Do not rush it.

## 1:10 — The catch (55s) — the heart of it

Back to the app, on the **Console**. In the DEMO strip, click **Replay: shipping swap**.

Say the honest thing once, early, then move on:

> "This particular failure is a captured scenario replayed offline — we can't make Newegg redesign on
> cue. The data is their real data; the guardian running on it is the real guardian."

A held decision appears with its **Verdict Seal**. Read it:

```
   MSI RTX 5090 · vs Newegg
   Our price        $6,900.00
   Competitor price ⚠ couldn't verify — came back $19.99 (the shipping cost)

   ╭ VERDICT · ✕ FAIL · trust 40/100 (Low) ╮
   the scraper mixed up two columns — read SHIPPING as the price
```

> "The heal worked — right rows, right shape, right types — and it silently started reading the
> shipping column. Newegg lists this card at sixty-nine hundred dollars with $19.99 shipping. A
> repricer acting on that number matches a competitor that doesn't exist."

Click **Show the damage**.

> "Our floor rule would have clamped us to $6,048 rather than following it down — margin twenty
> percent to seven. Without a floor you go to $19.98. A floor caps the disaster; only checking the
> number prevents it. And the chart refuses to draw a line across the cycle it couldn't verify —
> that's a hole in the data, not a guess."

## 2:05 — The re-prompt (20s) — quick, don't cut it

Click **Investigate**, then **Re-prompt & resume**.

> "Here's the guardian's working — proposed median zero against a historical eight hundred and ten —
> and the instruction it wrote back to Scraper Studio from those numbers. The validator writes the
> scraper's next prompt."

The second heal passes, the hold clears, a real proposal appears.

> "Sharper prompt, re-validated, confidence 100 — now it's a change the seller can act on."

## 2:25 — The reframe (25s) — the new heart

On the held card, click **`view as API →`**. It opens the **Trust API** view on the same row.

> "Everything you just saw hangs on one thing — this verdict. And it isn't buried in the repricer.
> It's a standalone call. Same rows, live —" (the response renders) "— `POST /verify`: decision
> fail, confidence forty, and the reason. This part is not replayed; that's the real endpoint.
> The repricer is just one consumer of this verdict. A pricing pipeline, an inventory system, an AI
> agent — anything that acts on scraped data can gate on it. That's the product."

## 2:50 — Close + what's next (10s)

> "Scraper Studio keeps the data flowing when a site changes. Vouch makes sure it didn't quietly
> start lying — a trust layer for any scraped-data pipeline. Repricing today; branded catalogs next."

End on the Verdict Seal, or the collector id.

---

## Rules for the recording

- **Never show a replay button before you have shown real CLI output.** Order is the whole
  credibility argument.
- **Say "replayed" once, early, plainly** — for the *heal*. Then note the **`/verify` beat is live**;
  the contrast helps, not hurts.
- **Don't say "we studied what wins hackathons."** Not in the video, not in Q&A.
- **Rehearse twice on the machine you'll record on.** `./demo.sh --reset` returns the app to the
  opening state between takes. Run the main catch with the live-derived dataset (the $6,900 card).

## The optional beat (Q&A, or if you have 30s spare)

Against the hand-written dataset (`DEMO_DATASET=sample_runs`) there is a fourth control: **Replay:
crossed-out price**. The heal reads the struck-through original instead of the sale price — only
~14% off.

> "This is the one a distribution check cannot catch. Fourteen percent is a plausible move, so
> nothing statistical fires. What catches it is an invariant: a sale price can never exceed the price
> it's discounted from. And the harm flips — here we'd price *above* the market and lose the sale,
> not undercut ourselves. No floor rule helps in that direction."

It is absent from the live-derived dataset on purpose: the real collector never captured
`original_price`, so the console does not offer a control its data cannot honour. That is the same
honesty the product is built on — worth saying if anyone asks.
