#!/usr/bin/env python3
"""
Build a browsable preview of every testbed variant, each with the guardian's real verdict.

    python preview.py            # writes preview/ and prints the serve command
    python preview.py --serve    # ...and serves it on http://127.0.0.1:8899

This is the testbed made visible: eight pages that differ by exactly one broken thing, an index that
puts the verdicts side by side, and a diff of what actually changed in the rows. Useful for seeing
what a break looks like to a human before seeing what it looks like to the checks.

The verdicts here are not narrated - each one is computed by running run_all_checks + decide over the
parsed page, the same code path the live gate uses.
"""

from __future__ import annotations

import argparse
import html
import shutil
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIEW = HERE / "preview"

from generate import VARIANTS, apply_variant, base_rows, render  # noqa: E402
from verify import parse                                          # noqa: E402

sys.path.insert(0, str(HERE.parent / "backend"))
from app.guardian.checks import profile_run, run_all_checks       # noqa: E402
from app.guardian.verdict import decide                            # noqa: E402

TONE = {"pass": ("#6fd39a", "PASS"), "review": ("#ffc857", "REVIEW"), "fail": ("#ff7a7a", "FAIL")}
SEV_TONE = {"critical": "#ff7a7a", "high": "#ff9f5c", "medium": "#ffc857", "low": "#8b90a0"}


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _row_delta(clean: list[dict], broken: list[dict]) -> list[str]:
    """Describe how the parsed rows changed, field by field, without dumping 30 rows."""
    if not clean or not broken:
        return []
    notes = []
    fields = sorted(set(clean[0]) | set(broken[0]))
    for f in fields:
        c = [r.get(f) for r in clean]
        b = [r.get(f) for r in broken]
        if c == b:
            continue
        c_nulls = sum(1 for v in c if v is None)
        b_nulls = sum(1 for v in b if v is None)
        nums_b = [v for v in b if isinstance(v, (int, float)) and not isinstance(v, bool)]
        nums_c = [v for v in c if isinstance(v, (int, float)) and not isinstance(v, bool)]
        bits = []
        if b_nulls != c_nulls:
            bits.append(f"nulls {c_nulls}/{len(c)} → {b_nulls}/{len(b)}")
        if nums_c and nums_b:
            bits.append(f"median {statistics.median(nums_c):,.2f} → {statistics.median(nums_b):,.2f}")
        elif not nums_b and nums_c:
            bits.append("numeric values gone")
        if not bits:
            uc, ub = len(set(map(str, c))), len(set(map(str, b)))
            bits.append(f"{uc} distinct → {ub} distinct")
        notes.append(f"{f}: " + ", ".join(bits))
    return notes


def build() -> list[dict]:
    if PREVIEW.exists():
        shutil.rmtree(PREVIEW)
    PREVIEW.mkdir(parents=True)

    clean_rows = parse(render(apply_variant(base_rows(), "clean"), "clean"))
    baseline = profile_run(clean_rows)
    baseline_count = len(clean_rows)

    # The pre-sale record: what the clean page charged, per product. In production this comes from
    # the confirmed CompetitorObservation rows. Supplied only to the sale variant, because an
    # ordinary heal has no sale claim to audit.
    before_sale = {r["name"]: r["price"] for r in clean_rows
                   if r.get("name") and r.get("price") is not None}

    results = []
    for variant, desc in VARIANTS.items():
        page = render(apply_variant(base_rows(), variant), variant)
        (PREVIEW / f"{variant}.html").write_text(page, encoding="utf-8")

        rows = parse(page)
        refs = before_sale if variant == "fake_sale" else None
        verdict = decide(run_all_checks(baseline, rows, baseline_count, reference_prices=refs))
        results.append({
            "variant": variant,
            "desc": desc,
            "rows": rows,
            "verdict": verdict,
            "delta": [] if variant == "clean" else _row_delta(clean_rows, rows),
        })

    (PREVIEW / "index.html").write_text(_index(results, baseline_count), encoding="utf-8")
    return results


def _index(results: list[dict], baseline_count: int) -> str:
    cards = []
    for r in results:
        v = r["verdict"]
        colour, label = TONE[v.decision]
        fails = "".join(
            f'<li><span class="sev" style="color:{SEV_TONE[f.severity.value]}">'
            f'{f.severity.value}</span> <code>{f.code}</code> '
            f'<span class="fld">{html.escape(f.field_name)}</span>'
            f'<div class="msg">{html.escape(f.message)}</div></li>'
            for f in v.failures
        ) or '<li class="none">no findings</li>'
        delta = "".join(f"<li>{html.escape(d)}</li>" for d in r["delta"])
        delta_block = f'<div class="delta"><h4>what changed in the rows</h4><ul>{delta}</ul></div>' if delta else ""
        pct = v.confidence

        return_note = ""
        if r["variant"] == "fake_sale":
            # PASS here is the designed outcome, not a gap: the extraction is right, the SITE's claim
            # is what is unsupported. Holding the repair would punish a good scrape.
            return_note = ('<div class="ok-note">PASS is correct here. We read the page exactly as '
                           'written, so the heal is sound — the finding is about the retailer\'s '
                           'claim, not our extraction.</div>')
        elif v.decision == "pass" and v.failures:
            return_note = ('<div class="warn">Detected, but still scored PASS — a lone medium '
                           'finding costs 10 and PASS needs only &ge;85, so nothing would be held.</div>')

        cards.append(f"""    <section class="card">
      <div class="head">
        <h3>{r['variant']}</h3>
        <a class="open" href="{r['variant']}.html" target="_blank">open the page &rarr;</a>
      </div>
      <p class="desc">{html.escape(r['desc'])}</p>
      <div class="verdict">
        <span class="badge" style="background:{colour}1f;color:{colour};border-color:{colour}55">{label}</span>
        <span class="score">{pct}<span class="of">/100</span></span>
        <div class="meter"><i style="width:{pct}%;background:{colour}"></i></div>
      </div>
      <p class="brief">{html.escape(v.brief)}</p>
      {return_note}
      <h4>findings</h4>
      <ul class="fails">{fails}</ul>
      {delta_block}
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voltmart testbed — all variants</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0b0a10; color:#e8eaf0;
    font:15px/1.55 ui-sans-serif, system-ui, "Segoe UI", sans-serif; }}
  header {{ padding:30px 32px 8px; }}
  h1 {{ margin:0 0 6px; font-size:24px; letter-spacing:-0.02em; }}
  .sub {{ color:#8b90a0; font-size:13.5px; max-width:70ch; }}
  .sub code {{ color:#a08cff; }}
  main {{ padding:22px 32px 60px; display:grid; gap:16px;
    grid-template-columns:repeat(auto-fill,minmax(410px,1fr)); align-items:start; }}
  .card {{ background:#14171e; border:1px solid #23262f; border-radius:12px; padding:17px 18px; }}
  .head {{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; }}
  h3 {{ margin:0; font-size:16px; font-family:ui-monospace,monospace; color:#a08cff; }}
  .open {{ font-size:12.5px; color:#8b90a0; text-decoration:none; white-space:nowrap; }}
  .open:hover {{ color:#a08cff; }}
  .desc {{ color:#8b90a0; font-size:12.5px; margin:5px 0 13px; font-family:ui-monospace,monospace; }}
  .verdict {{ display:flex; align-items:center; gap:11px; margin-bottom:9px; }}
  .badge {{ font-size:11.5px; font-weight:700; letter-spacing:0.07em; padding:3px 9px;
    border-radius:5px; border:1px solid; }}
  .score {{ font-size:22px; font-weight:700; font-variant-numeric:tabular-nums;
    font-family:ui-monospace,monospace; }}
  .of {{ font-size:12px; color:#6a6f7e; font-weight:400; }}
  .meter {{ flex:1; height:5px; background:#23262f; border-radius:3px; overflow:hidden; }}
  .meter i {{ display:block; height:100%; }}
  .brief {{ font-size:13.5px; margin:0 0 11px; }}
  .warn {{ font-size:12px; color:#ffc857; background:rgba(255,200,87,0.09);
    border:1px solid rgba(255,200,87,0.25); border-radius:7px; padding:8px 10px; margin-bottom:11px; }}
  .ok-note {{ font-size:12px; color:#6fd39a; background:rgba(111,211,154,0.08);
    border:1px solid rgba(111,211,154,0.22); border-radius:7px; padding:8px 10px; margin-bottom:11px; }}
  h4 {{ font-size:10.5px; text-transform:uppercase; letter-spacing:0.09em; color:#6a6f7e;
    margin:13px 0 6px; }}
  ul {{ list-style:none; margin:0; padding:0; }}
  .fails li {{ padding:7px 0; border-top:1px solid #1d202880; font-size:12.5px; }}
  .fails li.none {{ color:#6a6f7e; }}
  .sev {{ font-size:10.5px; text-transform:uppercase; letter-spacing:0.06em; font-weight:700; }}
  code {{ font-family:ui-monospace,"JetBrains Mono",monospace; color:#cdd2e0; font-size:12px; }}
  .fld {{ color:#8b90a0; font-size:11.5px; }}
  .msg {{ color:#8b90a0; font-size:12px; margin-top:2px; }}
  .delta ul li {{ font-size:12px; color:#8b90a0; padding:3px 0;
    font-family:ui-monospace,monospace; }}
</style>
</head>
<body>
<header>
  <h1>Voltmart testbed — every variant, every verdict</h1>
  <p class="sub">
    Eight pages that differ by exactly one broken thing. Each verdict below is computed by running
    <code>run_all_checks</code> + <code>decide</code> over the parsed page — the same code path the
    live approval gate uses, against a {baseline_count}-row baseline captured from
    <code>clean</code>. Nothing here is narrated.
  </p>
</header>
<main>
{chr(10).join(cards)}
</main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true", help="serve preview/ after building")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args(argv)

    results = build()
    width = max(len(r["variant"]) for r in results)
    print(f"built {PREVIEW}  ({len(results)} variants)\n")
    for r in results:
        v = r["verdict"]
        print(f"  {r['variant']:{width}}  {v.decision.upper():6} {v.confidence:>3}/100  "
              f"{(v.primary_failure.code if v.primary_failure else '-')}")
    print()

    if not args.serve:
        print(f"to view:  python -m http.server {args.port} --directory preview")
        print(f"then open http://127.0.0.1:{args.port}/")
        return

    import functools
    import http.server
    import socketserver

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(PREVIEW))
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving http://127.0.0.1:{args.port}/   (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
