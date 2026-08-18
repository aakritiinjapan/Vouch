"""
Repricing rules. Deliberately simple for the hackathon — the intelligence is in the guardian,
not here. The one rule that matters: never propose a price that breaks the floor margin.

Claude Code: extend with strategy (undercut by X, match, hold) as time allows, but keep the floor.
"""

from __future__ import annotations

from typing import Optional


def propose_price(product, competitor_price: Optional[float]) -> tuple[float, str]:
    """
    Return (new_price, human_reason).

    Strategy for the demo: undercut the competitor by a small margin, but never below the floor.
    """
    floor = round(product.cost * (1 + product.floor_margin), 2)

    if competitor_price is None:
        return product.my_price, "No confirmed competitor price this cycle — leaving price unchanged."

    target = round(competitor_price - 0.01, 2)     # undercut by a cent
    if target < floor:
        return floor, (f"Competitor at ${competitor_price:.2f} would push us below our floor "
                       f"(${floor:.2f}) — holding at the floor to protect margin.")

    if abs(target - product.my_price) < 0.01:
        return product.my_price, "Already competitively priced — no change needed."

    direction = "down" if target < product.my_price else "up"
    return target, (f"Competitor at ${competitor_price:.2f}; moving {direction} to ${target:.2f} "
                    f"to stay just under them while holding margin.")
