# Demo script (3 minutes)

Three minutes, not five. Judges watch a lot of these, and the arc lands harder tight.

The order matters more than anything else here: **prove the collector is real in the first 45
seconds, then let the product tell the story.** Leading with the dashboard invites the question "is
any of this actually Bright Data?" and you spend the rest of the video answering it.

Two windows: a terminal with real CLI output (captured in advance — see
[`LIVE_CAPTURE.md`](LIVE_CAPTURE.md)) and the console at `http://127.0.0.1:5173`.

---

## The arc

> A real collector → a real heal stopping at the approval gate → the guardian catching a heal that
> would have repriced a $6,900 card to $19.99 → the re-prompt that fixes it.

---

## 0:00 — The product, on real data (20s)

Console already loaded, in the confirmed state. Nothing held.

> "This is a repricer. It watches competitor prices and proposes changes — but only off data it can
> vouch for. The competitor data comes from a Scraper Studio collector I built from the CLI."

The collector id sits under the title. Let it be visible.

## 0:20 — The collector is real (25s)

Cut to the terminal. Real `scraper run` output scrolling — 96 graphics cards, names, prices,
shipping, stock.

> "Ninety-six cards off Newegg's public category page, one request."

## 0:45 — The heal stops at the gate (30s) — the most important beat

Still in the terminal. Real `scraper heal`. It pauses at `awaiting_approval` and hands back
`preview_result`.

> "Scraper Studio heals itself when a page changes. Without `--auto-approve` it stops here and hands
> you `preview_result` — the rows the fix *would* produce. Scraper Studio's own approval screen shows
> you a code diff. The CLI gives you the data. That gap is where this whole product lives."

Nobody else in this hackathon will have found this. Do not rush it.

## 1:15 — The catch (60s) — the heart of it

Back to the console. Click **Replay: shipping swap**.

Say the honest thing once, early, then move on:

> "This particular failure is a captured scenario replayed offline — I can't make Newegg redesign on
> cue. The data is their real data; the guardian running on it is the real guardian."

Three held cards appear. Read the top one:

```
⏸  Reprice held · COLUMN_SWAP
    ZOTAC ARCTICSTORM AIO GeForce RTX 5090 32GB

    −$951.00     per unit of margin, on every one sold, had we auto-approved

    The healed price ($19.99) matches this competitor's SHIPPING column, not their item price.
    40 / 100  ✕ failed   ·   source: www.newegg.com · unconfirmed
```

> "The heal worked. Right rows, right format, right types — and it silently started reading the
> shipping column. Newegg lists this card at six thousand nine hundred dollars with nineteen
> ninety-nine shipping. A repricer acting on that number matches a competitor that doesn't exist."

Click **Show the damage** on the top card.

> "Our floor rule would have clamped us to $6,048 rather than following it all the way down — margin
> twenty percent to seven. Without a floor you go to $19.98. A floor caps the disaster; only checking
> the number prevents it. And notice the chart refuses to draw a line across the cycle it couldn't
> verify — that's a hole in the data, not a guess."

## 2:15 — The re-prompt (30s) — do not cut this

Click **Investigate** on the same card, then **Re-prompt & resume**.

> "Here's the guardian's working — the proposed median was zero, against a historical median of eight
> hundred and ten. And this is the instruction it wrote back to Scraper Studio from those numbers.
> The validator writes the scraper's next prompt."

The second heal passes, the holds clear as superseded, and normal proposals appear.

> "Sharper prompt, re-validated, confidence 100. Now it's a change the seller can act on."

## 2:45 — Close (15s)

> "Scraper Studio keeps the data flowing when a site changes. Vouch makes sure it didn't quietly
> start lying — inside a product where trusting the number is the whole job."

End with the collector id on screen.

---

## Rules for the recording

- **Never show a replay button before you have shown real CLI output.** Order is the whole
  credibility argument.
- **Say "replayed" once, early, plainly.** Pre-empting costs nothing; being caught costs the track.
- **Don't say "we studied what wins hackathons."** Not in the video, not in Q&A.
- **Rehearse twice on the machine you'll record on.** `./demo.sh --reset` returns the console to the
  opening state between takes.

## The optional beat (Q&A, or if you have 30s spare)

Against the hand-written dataset (`DEMO_DATASET=sample_runs`) there is a fourth control: **Replay:
crossed-out price**. The heal reads the struck-through original instead of the sale price — only
~14% off.

> "This is the one a distribution check cannot catch. Fourteen percent is a plausible price move, so
> nothing statistical fires. What catches it is an invariant: a sale price can never be higher than
> the price it's discounted from. And the harm flips — here we'd price *above* the market and lose
> the sale, not undercut ourselves. No floor rule helps in that direction."

It is absent from the live-derived dataset on purpose: the real collector never captured
`original_price`, so the console does not offer a control its data cannot honour. That is worth
saying out loud if anyone asks — it is the same honesty the product is built on.
