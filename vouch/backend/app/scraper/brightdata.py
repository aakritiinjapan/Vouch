"""
Thin wrapper around Bright Data Scraper Studio — the ONE external system Vouch depends on.

Real surface (confirmed against the Bright Data CLI / docs, Aug 2026):

    brightdata login
    brightdata scraper create <url> "<natural-language field description>"   -> returns collector_id (c_*)
    brightdata scraper run    <collector_id> <url> --json
    brightdata scraper heal   <collector_id> "<prompt>" --url <url> -o heal.json   (stops at approval gate)
    brightdata scraper approve                                                     (commits the pending heal)

  The heal loop maps to three API calls under the hood:
    POST /dca/collectors/{id}/refactor_template   (propose)
    GET  .../refactor_template/progress           (poll until "pending_answer")
    POST .../resume_automation_job                (approve OR reject)

  The collector_id is also the handle for the Scraper Studio API and the brightdata-sdk:
    async with BrightDataClient() as c:
        rows = await c.scraper_studio.run(collector="c_abc", input={"url": url})

TWO THINGS TO CONFIRM against a live collector before Phase 2 relies on them (see README §6):
  1. that heal.json (written with --url) contains the PROPOSED rows pre-approval — the guardian
     needs to see them to judge the heal. (Very likely yes: the human gate exists precisely so a
     person can inspect the fix first.)
  2. the exact reject payload for resume_automation_job.

MOCK_MODE: when settings.mock_mode is true, every function reads from tests/fixtures/sample_runs.json
instead of calling Bright Data. This keeps development offline/deterministic and lets the demo run
without depending on a live site breaking on cue. Build everything in mock first.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import settings

_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sample_runs.json"


@dataclass
class HealProposal:
    collector_id: str
    proposed_records: list[dict]     # what the healed collector would return (for the guardian to judge)
    pending: bool = True             # sitting at the approval gate, not yet committed


# --------------------------------------------------------------------------------------
# MOCK helpers
# --------------------------------------------------------------------------------------

def _fixture(key: str) -> list[dict]:
    data = json.loads(_FIXTURES.read_text())
    return data[key]


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------

def run(collector_id: str, url: str) -> list[dict]:
    """Run a collector against a URL and return the extracted rows."""
    if settings.mock_mode:
        # in mock, the "current" run is the baseline (healthy) unless a break is simulated
        return _fixture("baseline")

    # --- real path (pick ONE; SDK shown, CLI fallback commented) -----------------------
    # from brightdata import BrightDataClient   # brightdata-sdk
    # async def _go():
    #     async with BrightDataClient() as c:
    #         return await c.scraper_studio.run(collector=collector_id, input={"url": url})
    # return asyncio.run(_go())
    out = _cli("scraper", "run", collector_id, url, "--json")
    return json.loads(out)


def propose_heal(collector_id: str, prompt: str, url: str,
                 _simulate: Optional[str] = None) -> HealProposal:
    """
    Trigger a self-heal. Returns the PROPOSED rows without committing (heal stops at the gate).

    _simulate (mock only): 'healed_good' | 'healed_swapped' — which fixture the fake heal returns,
    so the demo can deterministically produce either a clean heal or the dangerous swap.
    """
    if settings.mock_mode:
        key = _simulate or "healed_good"
        return HealProposal(collector_id=collector_id, proposed_records=_fixture(key), pending=True)

    heal_out = Path("heal.json")
    _cli("scraper", "heal", collector_id, prompt, "--url", url, "-o", str(heal_out))
    proposed = json.loads(heal_out.read_text())   # ⚠️ confirm this carries proposed rows (README §6)
    return HealProposal(collector_id=collector_id, proposed_records=proposed, pending=True)


def approve_heal(collector_id: str) -> None:
    """Commit the pending heal (same collector_id keeps working, now fixed)."""
    if settings.mock_mode:
        return
    _cli("scraper", "approve")


def reject_heal(collector_id: str) -> None:
    """Discard the pending heal; the old collector is retained."""
    if settings.mock_mode:
        return
    # exact reject payload for resume_automation_job — confirm against docs (README §6)
    _cli("scraper", "approve", "--reject")   # placeholder flag; verify real syntax


# --------------------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------------------

def _cli(*args: str) -> str:
    """Invoke the Bright Data CLI. Runs unchanged inside a coding-agent terminal; uses npx so
    there's nothing to install globally."""
    cmd = ["npx", "@brightdata/cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"brightdata {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout
