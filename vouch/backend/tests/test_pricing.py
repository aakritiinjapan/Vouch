"""
The floor rule in pricing/engine.py is the one line of code standing between a bad competitor price
and the seller's margin, and it was untested. These tests pin all four of its branches.
"""

from __future__ import annotations

from app.models import Product
from app.pricing import engine


def _product(**overrides) -> Product:
    base = dict(sku="GPU-5080-MSI", name="MSI RTX 5080 Gaming Trio", my_price=1299.98,
                cost=1050.00, floor_margin=0.08, competitor_url="https://example.com/x")
    return Product(**{**base, **overrides})


def test_floor_is_cost_plus_margin():
    assert round(_product().cost * 1.08, 2) == 1134.00


def test_undercuts_competitor_by_a_cent():
    price, reason = engine.propose_price(_product(), 1200.00)
    assert price == 1199.99
    assert reason


def test_competitor_below_floor_clamps_to_floor_and_says_so():
    """The demo's dangerous number. A repricer with no floor rule would follow it down to $19.98;
    ours must clamp - and the reason string has to explain the clamp, or the UI cannot narrate it."""
    price, reason = engine.propose_price(_product(), 19.99)
    assert price == 1134.00, "must never follow a bad competitor price below the floor"
    assert "floor" in reason.lower()


def test_no_competitor_price_leaves_price_untouched():
    product = _product()
    price, reason = engine.propose_price(product, None)
    assert price == product.my_price
    assert reason


def test_already_competitive_is_a_no_op():
    """Guards the exception-based queue: a matching price must not generate a proposal to review."""
    product = _product(my_price=1199.99)
    price, _ = engine.propose_price(product, 1200.00)
    assert price == product.my_price


def test_non_finite_competitor_price_cannot_escape_the_floor():
    """NaN and infinity are the floor rule's blind spot, and they fail OPEN.

    Every comparison against NaN is False, so `target < floor` answers "no" and the clamp above never
    runs - the engine hands back NaN as a price. Infinity survives the same way and is worse, because
    SQLite will happily store it: it reaches the product row, and serialises as the literal
    `Infinity`, which is not valid JSON for the client that has to read it back.

    These are not exotic. _coerce_number() parses "NaN", "inf" and "1e400" into exactly these values,
    so a single garbage cell on the competitor's page is enough to produce one.
    """
    product = _product()
    floor = 1134.00

    for bad in (float("nan"), float("inf"), float("-inf")):
        price, reason = engine.propose_price(product, bad)
        assert price == price, f"{bad} produced a NaN price"          # NaN != NaN
        assert price >= floor, f"{bad} produced {price}, under the floor {floor}"
        assert price in (product.my_price, floor), (
            f"{bad} is not a price; the engine must not move money on it (got {price})")
        assert reason


def test_zero_or_negative_competitor_price_clamps_to_the_floor():
    """A $0.00 read is garbage, not a competitor undercutting us to free.

    The floor is what makes it survivable, so pin that it actually catches this: without the clamp a
    zero would propose a zero, and the reason string has to name the floor or the UI cannot narrate
    why the price did not follow the competitor down.
    """
    for bad in (0.0, -1.0, 0.01):
        price, reason = engine.propose_price(_product(), bad)
        assert price == 1134.00, f"competitor {bad} must clamp to the floor, got {price}"
        assert "floor" in reason.lower()
