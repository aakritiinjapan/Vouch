# heal-failure research — run registry

Does Bright Data's self-heal fail in a PATTERN? Artifacts here are raw evidence, not conclusions.

Every collector below was created against the CLEAN Voltmart layout, so its stored template is
correct at baseline. The adversarial page is deployed to the SAME url afterwards — that ordering is
the experiment: the collector must be right first, or a wrong heal proves nothing.

| Hypothesis | URL | Collector | Baseline |
|---|---|---|---|
| P1 first-tile overfit | https://vouch-voltmart.netlify.app/p1.html | `c_mt5gwa3w1eknnqzr2` | `collector_p1.json` |
| P2 label-stripped / positional anchoring | https://vouch-voltmart.netlify.app/p2.html | `c_mt5gye8j2jjqinpxz9` | `collector_p2.json` |
| P3 stale cached DOM | https://vouch-voltmart.netlify.app/p3.html | `c_mt5gyg1d1web67uas2` | `collector_p3.json` |

All three returned the same 30 rows and the same six fields, so any later divergence is attributable
to the page edit or the heal, not to a collector that started out different.

There is no programmatic delete. These three are permanent until removed by hand at
https://brightdata.com/cp/scrapers — do not create more without a reason.

## Corrections to docs/BRIGHT_DATA_NOTES.md, measured here

- AI generation took **66-94 seconds**, not the documented 5-10 minutes. Timeouts sized for the
  documented figure are ~10x too generous.
- `budget balance` returns **403** with this API key, so spend cannot be polled. Credits are tracked
  by counting page loads instead.
- Collectors CAN be listed: `GET /dca/collectors_list`. Notes section 3 says otherwise.
- Heal prompts cap at **1000 chars** (`PROMPT_MAX_LEN`), separate from create's 500.
- `scraper approve` without `--auto-save` lands the heal in a DRAFT, not production. Our
  `approve_heal()` omits the flag while its docstring claims it commits.

## Heal pipeline stages, observed live

`planner` -> `control_preview_runner` -> `code_fixer` -> ...

`control_preview_runner` runs BEFORE `code_fixer`: the healer samples current behaviour, then writes
the fix against that sample. If that sample is row-limited the way `preview_result` is, it is the
mechanism P1 predicts.
