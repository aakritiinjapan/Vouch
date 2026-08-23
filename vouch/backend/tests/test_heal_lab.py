"""
Calibrate the heal-lab classifier before it is used to make claims about Bright Data.

`_classify` is the measuring instrument: it decides which baseline field a heal's output actually
resembles, and every conclusion the lab reports rests on it. If it mislabels a known swap then a
tally built from it is worse than no data - it would let us assert a pattern that is an artefact of
our own measurement. So it is checked against corruptions whose right answer we already know.
"""

import sys
from pathlib import Path

import pytest

TESTBED = Path(__file__).resolve().parents[2] / "testbed"
sys.path.insert(0, str(TESTBED))

from app.guardian.checks import profile_run  # noqa: E402
from scripts.heal_lab import PROMPT_FAMILIES, _classify  # noqa: E402

from generate import apply_variant, base_rows, render  # noqa: E402
from verify import parse  # noqa: E402


@pytest.fixture(scope="module")
def clean_rows():
    return parse(render(apply_variant(base_rows(), "clean"), "clean"))


@pytest.fixture(scope="module")
def baseline(clean_rows):
    return profile_run(clean_rows)


def _variant(name):
    return parse(render(apply_variant(base_rows(), name), name))


def test_an_honest_page_is_labelled_as_its_own_field(clean_rows, baseline):
    got = _classify(clean_rows, baseline)
    assert got["looks_like"] == "price"
    assert got["distances"]["price"] < got["distances"]["shipping"]


def test_a_price_shipping_swap_is_labelled_shipping(baseline):
    """The canonical mis-heal: the healer grabbed the delivery line."""
    got = _classify(_variant("swap"), baseline)
    assert got["looks_like"] == "shipping"


def test_a_crossed_out_swap_is_not_labelled_shipping(baseline):
    """price <-> original_price differ by only 5-30%, so the label must not drift to a far field.

    It may legitimately land on `price` (the two are close by construction) - what would be WRONG is
    calling it `shipping` or `rating`, because that would invent a mis-heal of a kind that did not
    happen and put it in the tally.
    """
    got = _classify(_variant("inverted"), baseline)
    assert got["looks_like"] in {"price", "original_price"}
    assert got["looks_like"] not in {"shipping", "rating"}


def test_a_4x_inflation_is_reported_as_explained_by_nothing(baseline):
    """Drift is not a swap, and the label must not pretend otherwise.

    4x the price lands arithmetically NEARER baseline `original_price` than baseline `price`, simply
    because original_price is the higher field. Naming it would put a swap in the tally that never
    happened. So the proximity guard has to refuse the label and say what the nearest field was.
    """
    got = _classify(_variant("drift"), baseline)
    assert got["looks_like"] is None, "an inflation must not be labelled as a swap"
    assert got["nearest"] is not None, "but the nearest field is still worth recording"
    assert "no baseline field explains" in got["reason"]


def test_a_dropped_price_is_reported_as_unclassifiable_not_guessed(baseline):
    """No price means no label. Guessing here would manufacture evidence."""
    rows = [{k: v for k, v in r.items() if k != "price"} for r in _variant("clean")]
    got = _classify(rows, baseline)
    assert got["looks_like"] is None
    assert "not numeric" in got["reason"]


def test_a_nulled_price_is_reported_as_unclassifiable(baseline):
    rows = [{**r, "price": None} for r in _variant("clean")]
    got = _classify(rows, baseline)
    assert got["looks_like"] is None


def test_classifying_an_empty_run_does_not_raise(baseline):
    assert _classify([], baseline)["looks_like"] is None


def test_every_prompt_family_names_the_price_field():
    """A prompt that never mentions price is not probing what the lab claims to probe."""
    for family, prompt in PROMPT_FAMILIES.items():
        assert "price" in prompt.lower(), family


def test_the_misleading_families_are_actually_misleading():
    """These carry the experiment: clear instructions that are WRONG.

    If the healer obeys them it trusts the prompt over the page, which is a far more useful finding
    than "vague prompts are risky" - so they must not accidentally be phrased as good advice.
    """
    crossed = PROMPT_FAMILIES["misleading_crossed"].lower()
    assert "crossed-out" in crossed and "correct price" in crossed

    shipping = PROMPT_FAMILIES["misleading_shipping"].lower()
    assert "delivery charge" in shipping and "correct price" in shipping

    control = PROMPT_FAMILIES["control_sharp"].lower()
    assert "not the shipping cost" in control, "the control must exclude what the others invite"
