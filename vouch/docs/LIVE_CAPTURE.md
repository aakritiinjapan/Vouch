# Capturing the live Bright Data footage

Everything in the console runs offline against a replay of the real collector run. This document is
the other half: the short, supervised session that puts **real Scraper Studio output on camera**.

Run it yourself rather than leaving it to an unattended process. A heal costs real credits, and an
interrupted one can leave a collector sitting at an open approval gate.

Budget: about ten minutes, two terminal windows, one screen recording.

---

## 0. Before you record

```bash
# from the repository root
export BRIGHTDATA_API_KEY=...        # the CLI reads this one
export BRIGHTDATA_API_TOKEN=...      # same value; the Python SDK reads this one

cd vouch/backend
source .venv/bin/activate            # created by ./demo.sh
```

Check the CLI can authenticate before the camera is rolling:

```bash
npx -y @brightdata/cli scraper run c_mszq0z1x27brru3wab \
  "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96" \
  --sync --json | head -40
```

**Expected:** a JSON envelope with a `graphics_cards` array, each entry carrying `name`,
`price: {"value": …, "currency": "USD"}`, `shipping`, `rating`, `in_stock`.

**If it fails:**

| What you see | What it means |
|---|---|
| `401` / `Unauthorized` | the key is wrong or unset — `npx -y @brightdata/cli login` also works |
| `429 Cannot run more than N jobs in parallel` | AI-Flow caps concurrent create/heal at 3; wait and retry |
| an empty `rows` array | the page shape changed; check the URL still resolves in a browser |
| `FileNotFoundError: npx` on Windows | `npx` is a `.cmd` shim — run from Git Bash or PowerShell, not cmd.exe |

Do not go further until this returns rows. Everything below assumes it does.

---

## 1. Shot one — the collector is real (about 20 seconds of footage)

Widen the terminal first; the JSON should not wrap into noise.

```bash
npx -y @brightdata/cli scraper run c_mszq0z1x27brru3wab \
  "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96" \
  --sync --json | head -60
```

What to say over it: *"This is a Scraper Studio collector I built from the CLI — 96 graphics cards
off Newegg's public category page."*

Make sure the collector id `c_mszq0z1x27brru3wab` is legible on screen. That id is the submission's
proof of execution, so it should appear in the video at least once.

---

## 2. Shot two — the heal stops at the gate (about 30 seconds, the important one)

This is the beat nothing else in the field will have. The heal pauses **before committing** and
hands back `preview_result`: the rows the fixed scraper *would* return.

```bash
MOCK_MODE=false python -m scripts.live_heal --prompt-style vague
```

**Expected output**, in order:

```
collector : c_mszq0z1x27brru3wab
prompt    : ...the deliberately underspecified prompt...

triggering the heal (this stops at the approval gate, it does not commit) ...
  gate reached: 1 preview rows
  ... the guardian's verdict on those rows ...
rejecting the heal - the collector is left exactly as it was
```

What to say over it: *"Scraper Studio's own approval screen shows you a code diff. The CLI hands you
the rows the fix would actually produce — that's the gap this whole product lives in."*

Two things worth knowing before you film:

- **`preview_result` is one row**, not a full run. That is measured, not a limitation of our code —
  see [`BRIGHT_DATA_NOTES.md`](BRIGHT_DATA_NOTES.md) §2. The guardian handles it via `is_sample`.
- **The heal will probably pass.** Our vague prompt has produced a *correct* extraction every time we
  have run it. That is the guardian being right, not a missed detection, and it is worth saying so
  on camera — then cut to the replayed swap for the failure case.

The script **always rejects at the end**, so the collector is left untouched and you can run it
again. Never pass `--keep`, and never pass `--auto-approve` to the CLI: that commits without the
gate, which deletes the thing this product is.

---

## 3. If you want to try for a real failing heal

Optional, and strictly time-boxed — two attempts, then stop. You already have an honest replay and
the README states plainly that no real bad heal was manufactured.

```bash
MOCK_MODE=false python -m scripts.live_heal \
  --prompt "the price looks wrong, re-read it from the number shown next to the delivery info"
```

The intent is to aim the model at the shipping element. If it still extracts correctly, stop — that
outcome is not a failure of the demo, and chasing it burns credits against a 3-job concurrency cap.

---

## 4. After recording

```bash
# confirm the collector is still healthy and unchanged
npx -y @brightdata/cli scraper run c_mszq0z1x27brru3wab \
  "https://www.newegg.com/GPUs-Video-Graphics-Cards/SubCategory/ID-48?PageSize=96" \
  --sync --json | head -20
```

If that returns rows, nothing was committed and you are done.

If a run ever leaves a gate open — the process died mid-heal — close it explicitly:

```bash
npx -y @brightdata/cli scraper approve c_mszq0z1x27brru3wab --reject
```

Rejecting leaves the scraper exactly as it was. There is no programmatic rollback of an *approved*
heal, which is the whole reason Vouch validates before the gate rather than after it.

---

## What this footage is for

The submission rules ask that `scraper heal` be shown working, and that the collector be wired into
something real downstream. Shots one and two cover the first; the console covers the second. Lead
the video with this footage rather than the dashboard — prove the collector is real in the first 45
seconds, then let the product tell the rest of the story.
