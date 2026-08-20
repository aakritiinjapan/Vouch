r"""
Run the guard loop on a schedule. This is the collector treated as a live endpoint.

A Scraper Studio collector id is a production trigger, not a one-off command: the same c_* runs from
any language or scheduler with no deployment step. This is the piece that makes Vouch a service
rather than a script you invoke by hand.

Two ways to use it, depending on who owns the clock:

    # 1. Vouch owns it - long-running, useful in a terminal or a container
    python -m scripts.watch --every 15m

    # 2. The system owns it - one cycle then exit, for cron / Task Scheduler / a CI schedule
    python -m scripts.watch --once

Wiring it to a real scheduler:

    # cron, every 15 minutes
    */15 * * * *  cd /srv/vouch/backend && .venv/bin/python -m scripts.watch --once >> watch.log 2>&1

    # Windows Task Scheduler
    schtasks /create /tn "Vouch guard loop" /sc minute /mo 15 ^
      /tr "C:\path\to\backend\.venv\Scripts\python.exe -m scripts.watch --once"

Every cycle goes through the same guard: a degraded run heals behind the approval gate, the guardian
validates the proposed rows, and a source it cannot vouch for produces a HELD reprice rather than a
price change. Unattended operation is exactly where that matters - there is no human watching to
notice that a heal started reading the wrong column.
"""

from __future__ import annotations

import argparse
import re
import signal
import sys
import time
from datetime import datetime, timezone

from app.config import settings
from app.db import get_session, init_db
from app import service

_DURATION = re.compile(r"^(\d+)\s*([smh])$", re.I)
_UNITS = {"s": 1, "m": 60, "h": 3600}

# Below this the loop is hammering the target for no reason: Scraper Studio bills per page load, and
# competitor prices do not move every thirty seconds.
MIN_INTERVAL_SECONDS = 60

_stop = False


def _handle_signal(_signum, _frame) -> None:
    global _stop
    _stop = True
    print("\n  stopping after the current cycle ...", flush=True)


def parse_interval(text: str) -> int:
    """'30s' | '15m' | '2h' -> seconds."""
    match = _DURATION.match(text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"expected something like 30s, 15m or 2h - got {text!r}")
    seconds = int(match.group(1)) * _UNITS[match.group(2).lower()]
    if seconds < MIN_INTERVAL_SECONDS:
        raise argparse.ArgumentTypeError(
            f"{text} is below the {MIN_INTERVAL_SECONDS}s floor. Scraper Studio bills per page load "
            f"and competitor prices do not move that fast."
        )
    return seconds


def run_once() -> int:
    """One sweep over every product. Returns the number of reprices held."""
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with get_session() as session:
        records = service.run_all_cycles(session)

        held = 0
        for record in records:
            outcome = record.outcome
            if outcome.proposal is None:
                state = "no change"
            elif outcome.proposal.status == "held":
                state = f"HELD ({outcome.verdict.confidence if outcome.verdict else 0}/100)"
                held += 1
            else:
                state = f"proposed {outcome.proposal.proposed_price:.2f}"

            healed = f"  healed x{len(outcome.heal_attempts)}" if outcome.heal_attempts else ""
            print(f"  {stamp}  {record.sku:18} {state}{healed}", flush=True)

    if held:
        # The whole point of running unattended: say so loudly rather than leaving it in a UI nobody
        # is looking at.
        print(f"  {stamp}  ** {held} reprice(s) HELD - a competitor source could not be verified **",
              flush=True)
    return held


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true",
                       help="run one cycle and exit (let cron or Task Scheduler own the clock)")
    group.add_argument("--every", type=parse_interval, metavar="INTERVAL",
                       help="run forever on this interval, e.g. 15m")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="stop after this many cycles (useful in CI)")
    args = parser.parse_args(argv)

    init_db()
    mode = "MOCK_MODE (replaying the captured collector run)" if settings.mock_mode \
        else "LIVE (triggering the real collector)"
    print(f"vouch watch - {mode}", flush=True)

    if args.once:
        run_once()
        return

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    print(f"  every {args.every}s - Ctrl-C to stop", flush=True)

    cycles = 0
    while not _stop:
        try:
            run_once()
        except Exception as exc:                       # noqa: BLE001
            # A scheduler that dies on the first transient error is not a scheduler. Log and carry on;
            # the guardian's job is to hold prices, and it cannot do that if the loop is dead.
            print(f"  cycle failed, continuing: {exc}", file=sys.stderr, flush=True)

        cycles += 1
        if args.max_cycles is not None and cycles >= args.max_cycles:
            break

        # Sleep in short slices so Ctrl-C is responsive rather than waiting out a 15-minute nap.
        slept = 0
        while slept < args.every and not _stop:
            time.sleep(min(1, args.every - slept))
            slept += 1


if __name__ == "__main__":
    main()
