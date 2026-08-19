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
