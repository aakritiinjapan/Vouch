"""
Repricing rules. Deliberately simple — the intelligence is in the guardian, not here, and the
repricer is only the Trust API's reference consumer. The one rule that matters: never propose a
price that breaks the floor margin.
"""

from __future__ import annotations

import math
from typing import Optional


def propose_price(product, competitor_price: Optional[float]) -> tuple[float, str]:
    """
    Return (new_price, human_reason).

    Strategy for the demo: undercut the competitor by a small margin, but never below the floor.
    """
    floor = round(product.cost * (1 + product.floor_margin), 2)

    if competitor_price is None:
        return product.my_price, "No confirmed competitor price this cycle — leaving price unchanged."

    # NaN and infinity are not high or low prices, they are a failed parse wearing a float's clothes,
    # and they defeat the floor in the one way that matters: every comparison against NaN is False, so
    # `target < floor` below quietly answers "no" and the clamp never runs. The engine would hand back
    # NaN as a price — or infinity, which SQLite stores happily, reaches the product row, and
    # serialises as the literal `Infinity`, which is not valid JSON for whoever reads it back.
    # _coerce_number() turns "NaN", "inf" and "1e400" into exactly these, so one garbage cell on the
    # competitor's page is enough to produce one. Treat them as no price at all — the only branch in
    # this function that never moves money.
    if not math.isfinite(competitor_price):
        return product.my_price, (
            f"Competitor price came back as '{competitor_price}', which is not a number we can price "
            f"against — leaving price unchanged.")

    target = round(competitor_price - 0.01, 2)     # undercut by a cent
    if target < floor:
        return floor, (f"Competitor at ${competitor_price:.2f} would push us below our floor "
                       f"(${floor:.2f}) — holding at the floor to protect margin.")

    if abs(target - product.my_price) < 0.01:
        return product.my_price, "Already competitively priced — no change needed."

    direction = "down" if target < product.my_price else "up"
    return target, (f"Competitor at ${competitor_price:.2f}; moving {direction} to ${target:.2f} "
                    f"to stay just under them while holding margin.")
