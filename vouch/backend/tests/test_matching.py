"""
Matching a seeded product to a scraped row.

This is the quiet failure mode of going live. Exact-name matching works perfectly against a fixture we
wrote and fails against a real listing page, where titles carry variant text, marketing prefixes and
inconsistent punctuation. When it fails the symptom is not an error - it is "no confirmed competitor
price", which presents as a mysteriously empty queue.

The opposite error is worse: matching the WRONG product means repricing against something else
entirely, which is the exact category of harm Vouch exists to prevent. So every test here checks one
of two things - that a real match is found, or that an ambiguous one is refused outright.
"""

from __future__ import annotations

import pytest

from app.models import Product
from app.orchestrator import _extract_competitor_price, _match_score, _normalise


def _product(name: str) -> Product:
    return Product(sku="X", name=name, my_price=100.0, cost=50.0,
                   competitor_url="https://example.com/x")


def _rows(*pairs: tuple[str, float]) -> list[dict]:
    return [{"name": name, "price": price} for name, price in pairs]


# --------------------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("  MSI RTX 5080 Gaming Trio  ", "msi rtx 5080 gaming trio"),
    ("MSI RTX-5080 (Gaming Trio)", "msi rtx 5080 gaming trio"),
    ("MSI   RTX\t5080\nGaming  Trio", "msi rtx 5080 gaming trio"),
    ("Women's Floral Dress, 2-Pack!", "women s floral dress 2 pack"),
])
def test_normalise_collapses_the_noise(raw, expected):
    assert _normalise(raw) == expected


# --------------------------------------------------------------------------------------
# pass 1 - exact after normalisation
# --------------------------------------------------------------------------------------

def test_exact_match_after_normalisation():
    rows = _rows(("  MSI RTX-5080 (Gaming Trio) ", 1299.99), ("Other Card", 999.0))
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) == 1299.99


def test_currency_strings_are_coerced():
    """Real pages return "$1,299.99", not a float."""
    rows = [{"name": "MSI RTX 5080 Gaming Trio", "price": "$1,299.99"}]
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) == 1299.99


# --------------------------------------------------------------------------------------
# pass 2 - containment, the common real-world shape
# --------------------------------------------------------------------------------------

def test_a_listing_title_that_wraps_our_name_matches():
    """The single most common real case: the retailer pads the title we know."""
    rows = _rows(("MSI RTX 5080 Gaming Trio 16GB GDDR7 Graphics Card - Black", 1289.00))
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) == 1289.00


def test_containment_that_matches_two_rows_is_refused():
    """Two variants both contain our name, so which one is ours is genuinely unknown."""
    rows = _rows(("MSI RTX 5080 Gaming Trio 16GB", 1289.00),
                 ("MSI RTX 5080 Gaming Trio 24GB", 1489.00))
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) is None


# --------------------------------------------------------------------------------------
# pass 3 - token overlap, with a clear winner required
# --------------------------------------------------------------------------------------

def test_reordered_and_padded_titles_still_match():
    rows = _rows(("Gaming Trio RTX 5080 by MSI, 16GB", 1275.50), ("ASUS TUF RTX 5070", 599.0))
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) == 1275.50


def test_a_different_product_is_not_matched():
    """Below the threshold nothing is returned - an unconfirmed price beats a wrong one."""
    rows = _rows(("ASUS Prime RTX 5070 12GB", 599.00))
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) is None


def test_a_tie_is_refused_rather_than_picked_arbitrarily():
    """Two equally plausible candidates: choosing either would be a coin flip on the seller's money."""
    rows = _rows(("RTX 5080 Gaming Trio MSI variant A", 1200.0),
                 ("MSI Gaming Trio RTX 5080 variant B", 1300.0))
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) is None


def test_marketing_noise_words_do_not_create_false_matches():
    """'Women' / 'Plus Size' / 'New' appear on half a fashion listing; they identify nothing."""
    assert _match_score("Women Plus Size New Floral Dress",
                        "Women Plus Size New Striped Trousers") < 0.6


def test_fashion_titles_match_on_their_identifying_words():
    rows = _rows(("SHEIN Ladies Floral Print Chiffon Midi Dress - Blue, Size M", 12.99),
                 ("SHEIN Solid Ribbed Knit Cardigan", 18.50))
    product = _product("Floral Print Chiffon Midi Dress")
    assert _extract_competitor_price(product, rows) == 12.99


# --------------------------------------------------------------------------------------
# empty and malformed input
# --------------------------------------------------------------------------------------

def test_no_rows_yields_no_price():
    assert _extract_competitor_price(_product("Anything"), []) is None


def test_rows_without_names_yield_no_price():
    assert _extract_competitor_price(_product("Anything"), [{"price": 10.0}]) is None


def test_an_unparseable_price_yields_none_not_a_crash():
    rows = [{"name": "MSI RTX 5080 Gaming Trio", "price": "Currently unavailable"}]
    assert _extract_competitor_price(_product("MSI RTX 5080 Gaming Trio"), rows) is None


def test_an_alternative_price_field_can_be_named():
    """Some pages expose the sale price under a different key than 'price'."""
    rows = [{"name": "Floral Dress", "sale_price": 9.99, "price": 24.99}]
    product = _product("Floral Dress")
    assert _extract_competitor_price(product, rows, price_field="sale_price") == 9.99
    assert _extract_competitor_price(product, rows) == 24.99
