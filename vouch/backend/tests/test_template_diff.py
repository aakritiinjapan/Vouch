"""
The template diff, held to the standard it sets for itself.

This module's own docstring says a plausible-looking WRONG finding is far more damaging than a
missing one. That is the claim these tests exist to keep honest, and it splits into two halves that
want completely different kinds of test:

  1. WHAT IT SAYS ABOUT THE SIX REAL HEALS. Pinned against the raw payloads in docs/research/, not
     against hand-written JavaScript. The measured table lives in `MEASURED` below and every row of
     it was verified by hand before it was written down. A hand-rolled approximation of Bright
     Data's generated code is a statement about what we expect it to emit, and expectations are
     exactly the thing under test - the same reasoning test_brightdata.py gives for loading the raw
     payloads rather than inventing them.

  2. WHETHER IT CAN BE MADE TO LIE. Two directions, and they are not symmetric. A false negative -
     "nothing changed" about a heal that repointed a field - is wired straight to
     `orchestrator._publishable`, where `not diff.is_semantic` is read as permission to publish off
     the gate without re-reading the page. A false positive costs one page load. So the tests attack
     the false-negative side hardest: malformed input, absent input, half input, source we cannot
     parse, and - the one that was actually broken - a genuine repoint that the cosmetic normaliser
     could not see.

Two defects were found this way and both are pinned with reproductions:

  * `_normalised` compared BLANKED text, in which string contents are NUL of the same length. Any
    two selectors of equal length were identical to it, so a crossed price/shipping swap between
    `.cost-now` and `.cost-shp` classified COSMETIC and summarised as "no code changed" while its own
    `field_changes` held both repoints. See `test_a_swap_between_equal_length_selectors_*`.
  * `is_semantic` was False for every "we could not read this", which spends an admission of
    ignorance as a clean bill of health. See `test_an_unreadable_diff_escalates_*`.

Nothing here spends a Bright Data credit; the module is pure stdlib over files already on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.guardian import template_diff as td
from app.guardian.template_diff import (
    ChangeClass,
    ExtractionStatus,
    diff_templates,
    parse_template,
)

# Same source of truth as test_brightdata.py, and load-bearing for the same reason: if these files
# go missing the tests must fail loudly rather than skip, because losing the evidence is a bigger
# problem than a red build.
RESEARCH = Path(__file__).resolve().parents[2] / "docs" / "research"


def captured(name: str) -> dict:
    """The `diff` object out of one raw heal payload, exactly as the CLI emitted it."""
    return json.loads((RESEARCH / name).read_text(encoding="utf-8"))["diff"]


def source(name: str) -> str:
    """One side of a heal as readable JavaScript, from the extracted .js files."""
    return (RESEARCH / name).read_text(encoding="utf-8")


def wrap(a: str, b: str) -> dict:
    """The minimum legacy-diff shape the module accepts, for tests that mutate the source."""
    return {"template_a": {"steps": [{"parse_code": a}]},
            "template_b": {"steps": [{"parse_code": b}]}}


# ======================================================================================
# 1. the six real heals
# ======================================================================================
#
# (payload, classification, has_swap, has_cross_field_repoint). Verified against the raw payloads on
# 2026-08-23 and cross-read against FINDINGS.md. Read the notes column as the reason each row is the
# row it is - a table of booleans with no reasons in it is a table nobody dares change.
MEASURED = [
    # the healthy-page probe: comments rewritten plus a defensive decimal guard, no field moved.
    ("heal_legacy_probe.json",     ChangeClass.LOGIC_ONLY, False, False),
    # P1, the CORRECT heal: the page swapped price and delivery in tile 1, and the healer answered
    # with a conditional on the literal label text. Reports a swap, and was right.
    ("heal_p1.json",               ChangeClass.REPOINTED,  True,  True),
    # P2: no labels on the page at all, so the healer had only DOM order to work with. Positional,
    # and positionally CORRECT - which is why this must not read as a swap.
    ("heal_p2.json",               ChangeClass.REPOINTED,  False, False),
    # P3: every class on the page renamed. Six repoints and the record selector moved, and no field
    # took over another field's element - the shape that is provably not a swap.
    ("heal_p3.json",               ChangeClass.REPOINTED,  False, False),
    # "the correct price is the delivery charge" - WRONG, and the one the 2-row gate passed at
    # 100/100. One field borrows another's element without giving anything back, so it is a
    # cross-field repoint but not a mutual swap.
    ("heal_mislead_shipping.json", ChangeClass.REPOINTED,  False, True),
    # "the correct price is the crossed-out number" - WRONG. price and original_price cross.
    ("heal_mislead_crossed.json",  ChangeClass.REPOINTED,  True,  True),
]


@pytest.mark.parametrize("payload,classification,has_swap,cross_field", MEASURED)
def test_the_six_captured_heals_classify_as_measured(payload, classification, has_swap, cross_field):
    """The table, pinned. Every row of it is a real heal that really happened."""
    result = diff_templates(captured(payload))

    assert result.status is ExtractionStatus.OK, "all six are shapes we can read"
    assert result.classification is classification
    assert result.has_swap is has_swap
    assert result.has_cross_field_repoint is cross_field


@pytest.mark.parametrize("payload,classification,_swap,_cross", MEASURED)
def test_every_captured_heal_resolves_every_field(payload, classification, _swap, _cross):
    """No `unresolved_fields` on any real payload.

    This is the coverage claim the module rests on: it says it recognises the idiom Bright Data's
    generator emits and declines on everything else. If a real heal starts landing in the declining
    branch, the escalation still fires (see the honesty tests) but the field-level evidence is gone,
    and that is worth knowing about as a failure rather than as a quietly shorter brief.
    """
    result = diff_templates(captured(payload))

    assert result.unresolved_fields == ()
    assert {f.name for f in result.template_b.fields} == {
        "name", "price", "original_price", "shipping", "rating", "in_stock"}


def test_the_healthy_probe_is_neither_a_repoint_nor_merely_cosmetic():
    """LOGIC_ONLY is a third thing and the study is why it has to exist.

    The probe added a decimal guard - real code, in the parser, doing arithmetic on the price - and
    rewrote comments. "Cosmetic" would overstate how much we read; "repointed" would spend a page
    load on a heal the source has cleared. Saying so precisely is what keeps the channel worth
    reading.
    """
    result = diff_templates(captured("heal_legacy_probe.json"))

    assert result.classification is ChangeClass.LOGIC_ONLY
    assert result.is_semantic is False, "no page load: no field reads anything new"
    assert result.is_cosmetic is False, "but it is not nothing either - code changed"
    assert result.field_changes == ()
    assert result.code_lines_changed > 0, "the decimal guard is real code"
    assert result.bullets() == [], "LOGIC_ONLY says nothing to the operator, by design"
    assert "no field was repointed" in result.summary


def test_the_misleading_shipping_heal_names_the_field_it_stole_from():
    """The one sentence this whole module exists to produce, verbatim.

    FINDINGS.md measured this heal scoring PASS 100/100 on the gate's two rows. In the SOURCE it is
    one line, and it is legible before a credit is spent. The wording matters as much as the finding:
    naming `shipping` as the previous owner is what turns "a selector changed" into something an
    operator can act on in two seconds.
    """
    result = diff_templates(captured("heal_mislead_shipping.json"))

    assert result.is_semantic is True
    assert "'price' now reads '.price-ship'" in result.summary
    assert "the element 'shipping' read before" in result.summary
    assert result.collisions == (("price", "shipping"),), "both fields now hold the same number"
    assert result.swapped_pairs == (), "shipping did not take price's element in return"

    price = next(c for c in result.field_changes if c.field == "price")
    assert price.before == (".price-current",)
    assert price.after == (".price-ship",)
    assert price.borrowed_from == ("shipping",)
    assert price.retained is False, "it did not keep its old element; it moved"


def test_the_crossed_heal_reports_a_mutual_swap_not_two_repoints():
    """A page rename can move both fields. It cannot make them cross.

    Which is why `swapped_pairs` is reported apart from the two `FieldChange`s that imply it: mutual
    borrowing is qualitatively stronger evidence, and collapsing it into "2 fields repointed" would
    file it beside P3's benign wholesale rename.
    """
    result = diff_templates(captured("heal_mislead_crossed.json"))

    assert result.swapped_pairs == (("original_price", "price"),)
    assert "now read each other's previous elements" in result.summary
    assert result.collisions == (), "they crossed; they did not both land on one element"
    assert {(c.field, c.before, c.after) for c in result.field_changes} == {
        # price took the crossed-out element, and original_price was handed the live one in return -
        # "the correct price is the crossed-out number", which produced $2,199.99 for a $1,999.99 GPU.
        ("price", (".price-current",), (".price-was",)),
        ("original_price", (".price-was",), (".price-current",)),
    }


def test_p1_reports_a_widening_rather_than_a_move():
    """P1's price did not move - it gained a second element behind a branch, and kept the first.

    Saying "'.price-current' -> '.price-ship'" here would be false in a way an operator cannot
    check: the field still reads its old element on 29 of 30 tiles. `retained` exists for this, and
    the study's correct heal is the reason it does.
    """
    result = diff_templates(captured("heal_p1.json"))

    price = next(c for c in result.field_changes if c.field == "price")
    assert price.retained is True
    assert price.before == (".price-current",)
    assert price.after == (".price-current", ".price-ship")
    assert price.conditional_now is True
    assert "still reads '.price-current', now ALSO reads '.price-ship'" in price.describe()
    assert "[branches on page content]" in price.describe()

    assert any("either the page swapped them or the heal did" in b for b in result.bullets()), \
        "the bullet must stay neutral - P1 is the heal where the page was the thing that swapped"


def test_p2_reports_positional_selection_as_the_fragility_it_is():
    """`.money:eq(1)` is correct today and one inserted span away from wrong tomorrow.

    P2's page had no labels, so position was the only answer available; FINDINGS.md is explicit that
    this is a floor measurement rather than a defect. What the operator needs to be told is not
    "this heal is bad" but "this heal now depends on DOM order", which is a different sentence.
    """
    result = diff_templates(captured("heal_p2.json"))

    assert result.has_cross_field_repoint is False, "correct positions, no borrowing"
    assert any("told apart only by their position" in n for n in result.notes)
    assert any("no new selector was previously read by another field" in n for n in result.notes), \
        "the reassuring half is worth saying out loud, or the operator only ever hears alarm"

    price = next(c for c in result.field_changes if c.field == "price")
    assert price.after == (".item-price .money:eq(1)",), "the modifier is part of the element"


def test_p3_renames_everything_and_is_provably_not_a_swap():
    """Six repoints, a moved record selector, and no borrowing anywhere.

    The loudest diff of the six and the most benign. That the module can say so from the source
    alone - no field took over an element another field already had, so no value can have moved
    between fields - is the difference between evidence and noise.
    """
    result = diff_templates(captured("heal_p3.json"))

    assert result.root_before == ".item" and result.root_after == ".prod-card"
    assert result.root_changed is True
    assert len(result.field_changes) == 6
    assert result.has_cross_field_repoint is False
    assert result.swapped_pairs == () and result.collisions == ()
    assert "the record selector moved from '.item' to '.prod-card'" in result.summary


# ======================================================================================
# 2. honesty - it must never report a confident empty diff
# ======================================================================================
#
# `orchestrator._publishable` reads `not diff.is_semantic` as PERMISSION TO SKIP THE FULL-PAGE RUN.
# Every case below is one where the module knows nothing, and the thing it must not do with "I know
# nothing" is spend it as "nothing changed".

MALFORMED = [
    ("none",                    None),
    ("empty dict",              {}),
    ("a list",                  []),
    ("a bare string",           "template_a"),
    ("an integer",              7),
    ("diff with neither side",  {"title": "heal", "user": "someone"}),
    ("template keys nested one level too deep", {"diff": {"title": "heal"}}),
]


@pytest.mark.parametrize("label,raw", MALFORMED)
def test_a_diff_that_was_never_returned_reports_no_diff_and_asserts_nothing(label, raw):
    """NO_DIFF is the ONE ignorance that does not escalate, and the distinction is deliberate.

    Nothing was offered - no `--legacy-output`, or a gate that returned a heal without one, which is
    every MOCK_MODE heal. Escalating on that would mean escalating on every heal in the demo path
    and on every caller who did not ask for source, which teaches the escalation to mean nothing.
    What it must still never do is make a POSITIVE claim, so: no classification, no summary that
    says "unchanged", and no bullets.
    """
    result = diff_templates(raw)

    assert result.status is ExtractionStatus.NO_DIFF
    assert result.classification is ChangeClass.UNKNOWN
    assert result.is_semantic is False
    assert result.is_cosmetic is False, "absence of a diff is not evidence of a cosmetic one"
    assert result.could_not_read is False, "we did not fail to read it; there was nothing to read"
    assert result.field_changes == () and result.bullets() == []
    assert "No template diff was returned" in result.summary


UNREADABLE = [
    # (label, raw_diff, expected status)
    ("only template_a arrived",
     {"template_a": {"steps": [{"parse_code": "return {a: $('.x').text(), b: 1};"}]}},
     ExtractionStatus.INCOMPLETE_DIFF),
    ("only template_b arrived",
     {"template_b": {"steps": [{"parse_code": "return {a: $('.x').text(), b: 1};"}]}},
     ExtractionStatus.INCOMPLETE_DIFF),
    ("a side is null",
     {"template_a": {"steps": [{"parse_code": "x"}]}, "template_b": None},
     ExtractionStatus.NO_PARSE_CODE),
    ("steps is empty",
     {"template_a": {"steps": []}, "template_b": {"steps": []}},
     ExtractionStatus.NO_PARSE_CODE),
    ("steps[0] is not an object",
     {"template_a": {"steps": [7]}, "template_b": {"steps": [7]}},
     ExtractionStatus.NO_PARSE_CODE),
    ("parse_code is absent from the step",
     {"template_a": {"steps": [{"name": "collect"}]}, "template_b": {"steps": [{"name": "collect"}]}},
     ExtractionStatus.NO_PARSE_CODE),
    ("parse_code is the empty string",
     {"template_a": {"steps": [{"parse_code": ""}]}, "template_b": {"steps": [{"parse_code": ""}]}},
     ExtractionStatus.NO_PARSE_CODE),
    ("parse_code is only whitespace",
     {"template_a": "   \n  ", "template_b": "\n\n"},
     ExtractionStatus.NO_PARSE_CODE),
]


@pytest.mark.parametrize("label,raw,status", UNREADABLE)
def test_an_unreadable_diff_escalates_instead_of_reading_as_unchanged(label, raw, status):
    """A diff arrived and we failed to read it. That is an admission, and it escalates like one.

    This was the module's most dangerous behaviour and it is worth stating plainly why. Before the
    fix every case here returned `is_semantic=False`, which `_publishable` reads as permission to
    publish off the gate without the full-page run. `--legacy-output` is undocumented; the likeliest
    way this module ever breaks is an upstream shape change, and that would have switched the whole
    escalation off at once, with no failing test and nothing in the brief to notice it had happened.

    Escalating costs one page load. Not escalating costs the verification step.
    """
    result = diff_templates(raw)

    assert result.status is status
    assert result.could_not_read is True
    assert result.is_semantic is True, "we cannot clear this heal, so the page has to answer"
    assert result.is_cosmetic is False
    assert result.has_demonstrated_repoint is False, "escalating is not the same as finding"
    assert result.field_changes == ()
    assert result.bullets() == [result.summary], \
        "an escalation with no stated cause is an operator staring at an unexplained page load"


def test_a_half_returned_diff_does_not_claim_that_no_diff_was_returned():
    """"No template diff was returned" about a response that returned one is a false sentence.

    It also disappears: `orchestrator` files NO_DIFF as "nothing worth recording" and drops the
    evidence, so a broken upstream response would leave no trace at all. A response carrying one
    side and not the other is a BROKEN response, and the missing side is precisely the one that
    would have said whether a field moved.
    """
    result = diff_templates({"template_a": {"steps": [{"parse_code": source("p1_template_a.js")}]}})

    assert result.status is ExtractionStatus.INCOMPLETE_DIFF
    assert result.status is not ExtractionStatus.NO_DIFF, "or the orchestrator will not record it"
    assert "missing its 'template_b' side" in result.summary
    assert result.is_semantic is True


UNPARSEABLE_JS = [
    ("an unterminated string literal", "let sel = 'oops;\nreturn {a: 1, b: 2};",
     ExtractionStatus.UNREADABLE_SOURCE),
    ("an unterminated block comment", "/* still going\nreturn {a: 1, b: 2};",
     ExtractionStatus.UNREADABLE_SOURCE),
    ("an unterminated template literal", "let sel = `.item\nreturn {a: 1, b: 2};",
     ExtractionStatus.UNREADABLE_SOURCE),
    ("no return object at all", "module.exports = function () { return 42; };",
     ExtractionStatus.UNRECOGNISED_SHAPE),
    ("a single-field record, indistinguishable from the container wrapper",
     "return { products: $('.item').toArray() };", ExtractionStatus.UNRECOGNISED_SHAPE),
    ("two equally plausible record objects",
     "if (x) { return {a: $('.p').text(), b: $('.q').text()}; }\n"
     "return {c: $('.r').text(), d: $('.s').text()};", ExtractionStatus.UNRECOGNISED_SHAPE),
]


@pytest.mark.parametrize("label,js,status", UNPARSEABLE_JS)
def test_javascript_outside_the_recognised_idiom_is_declined_not_guessed(label, js, status):
    """The scanner declines on anything it does not recognise, and the decline escalates.

    Each of these is a shape the module explicitly refuses to reason about: a literal that never
    closes means our model of the file is wrong somewhere, and an ambiguous record object means we
    cannot say which keys are data fields. Guessing would produce a finding that is
    indistinguishable, at the point of use, from a real one.
    """
    result = diff_templates(wrap(source("p1_template_a.js"), js))

    assert result.status is status
    assert result.is_semantic is True and result.is_cosmetic is False
    assert "judge this heal on its values alone" in result.summary


def test_a_field_read_through_a_computed_selector_is_declined_rather_than_reported():
    """`.find(someVariable)` is legal, opaque, and must not be reported alongside what we CAN see.

    The literal selectors in such an expression are not the whole story - the field's real source
    might be the one we cannot resolve - so the field is listed under `unresolved_fields` with a
    reason and no change is claimed about it either way.
    """
    dynamic = """
    let products = $('.grid .item').toArray().map(item => {
      let $item = $(item);
      let sel = window.PRICE_SELECTOR;
      return {
        name: $item.find('.item-title').text_sane(),
        price: $item.find(sel).text_sane(),
        shipping: $item.find('.price-ship').text_sane()
      };
    });
    return { products };
    """
    result = diff_templates(wrap(dynamic, dynamic.replace(".price-ship", ".delivery")))

    assert dict(result.unresolved_fields)["price"] == \
        "selector is computed at runtime, not a literal"
    assert [c.field for c in result.field_changes] == ["shipping"], \
        "the field we could read is still reported; the one we could not is not guessed at"
    assert any("not checked (source shape unfamiliar): price" in b for b in result.bullets())


def test_no_input_makes_it_raise():
    """A heal decision must not fall over because an undocumented field changed shape upstream.

    Breadth rather than depth: the point is that `diff_templates` is total over hostile input, so
    every branch returns a TemplateDiff and none of them throws on the way.
    """
    hostile = [
        None, 0, "", b"bytes", [], {}, {"template_a": 1, "template_b": 2},
        {"template_a": [], "template_b": []},
        {"template_a": {"steps": {"not": "a list"}}, "template_b": {"steps": None}},
        {"template_a": {"steps": [{"parse_code": None}]}, "template_b": {"steps": [{}]}},
        {"template_a": {"parse_code": "return {a: $('.x').t(), b: $('.y').t()};"},
         "template_b": {"parse_code": "return {a: $('.z').t(), b: $('.y').t()};"}},
        {"diff": {"template_a": "return {a: $('.x').t(), b: 1};", "template_b": "\x00\x00"}},
        wrap("return {a: $('.x').t(), b: 1};", "\\" * 500),
        wrap("(" * 400, ")" * 400),
        wrap("return {" + ",".join(f"f{i}: $('.c{i}').t()" for i in range(200)) + "};",
             "return {" + ",".join(f"f{i}: $('.d{i}').t()" for i in range(200)) + "};"),
    ]
    for raw in hostile:
        result = diff_templates(raw)
        assert isinstance(result.status, ExtractionStatus)
        assert isinstance(result.classification, ChangeClass)
        assert result.summary, "every outcome says something; silence is not an answer"
        json.dumps(result.to_dict()), "to_dict feeds a CheckResult's evidence - it must serialise"


def test_the_unknown_classification_never_claims_a_change_it_cannot_show():
    """UNKNOWN escalates, but it must not fabricate the finding that would justify the escalation.

    The distinction the brief has to preserve: `is_semantic` says "go and look", and
    `has_demonstrated_repoint` says "a field moved". Only the second one is a claim about the heal,
    and it is False for everything we could not read.
    """
    result = diff_templates(wrap(source("p3_template_a.js"), "function nope() { return 1; }"))

    assert result.classification is ChangeClass.UNKNOWN
    assert result.has_demonstrated_repoint is False
    assert result.swapped_pairs == () and result.collisions == ()
    assert result.has_cross_field_repoint is False
    assert result.to_dict()["semantic"] is True
    assert result.to_dict()["demonstrated_repoint"] is False


# ======================================================================================
# 3. the equal-length selector defect, reproduced
# ======================================================================================

def test_a_swap_between_equal_length_selectors_is_not_reported_as_cosmetic():
    """REGRESSION. This exact input classified COSMETIC, and it is a crossed price/shipping swap.

    `_normalised` compared the BLANKED source, in which a string literal's contents have been
    replaced by NUL of the same length. `.cost-now` and `.cost-shp` are both nine characters, so
    after blanking the two templates were byte-identical, `cosmetic_only` was True, and it won
    outright over a `field_changes` tuple holding both repoints. The emitted summary was:

        "Comments and formatting only (0 lines); no code changed."

    about a heal that swapped price and shipping. Not a missed finding - a confident denial, from
    the one module written to never produce one, wired to the boolean that skips verification.
    """
    a = source("p3_template_a.js").replace(".price-current", ".cost-now").replace(".price-ship", ".cost-shp")
    b = source("p3_template_a.js").replace(".price-current", ".cost-shp").replace(".price-ship", ".cost-now")
    assert len(".cost-now") == len(".cost-shp"), "the premise of the defect"

    result = diff_templates(wrap(a, b))

    assert result.classification is ChangeClass.REPOINTED
    assert result.is_cosmetic is False
    assert result.is_semantic is True
    assert result.swapped_pairs == (("price", "shipping"),)
    assert "no code changed" not in result.summary


def test_an_equal_length_rename_of_one_selector_is_not_reported_as_cosmetic():
    """The same defect at its smallest: one field, one selector, same character count."""
    a = source("p3_template_a.js")
    b = a.replace(".price-was", ".price-shp")
    assert a != b and len(".price-was") == len(".price-shp")

    result = diff_templates(wrap(a, b))

    assert result.is_semantic is True
    assert [(c.field, c.after) for c in result.field_changes] == \
        [("original_price", (".price-shp",))]


def test_whitespace_inside_a_selector_is_not_normalised_away():
    """Out-of-literal whitespace is noise; whitespace inside a selector is part of the selector.

    A signature that collapsed both would make `.grid .item` and `.grid  .item` identical, which is
    the same blind spot as the NUL one arriving by a different route. The module errs toward saying
    the element changed, because the cost of being wrong in that direction is one page load.
    """
    a = "return {a: $('.grid .item').t(), b: $('.x').t()};"
    b = "return {a: $('.grid  .item').t(), b: $('.x').t()};"

    result = diff_templates(wrap(a, b))

    assert result.is_cosmetic is False
    assert result.is_semantic is True


def test_a_demonstrated_repoint_outranks_the_cosmetic_heuristic():
    """Belt and braces, at the level of the branch rather than the normaliser.

    `field_changes` is a demonstration - two maps built the same way from both sides that disagree.
    `cosmetic_only` is a text heuristic. Closing the NUL hole should make a conflict unreachable;
    this pins the ORDER anyway, so that a normaliser which goes wrong again degrades into a spurious
    page load rather than into a denial.
    """
    src = td.__dict__["_code_signature"]
    original = src

    def always_equal(_s, _b):
        return "identical"

    td._code_signature = always_equal
    try:
        result = diff_templates(captured("heal_mislead_shipping.json"))
    finally:
        td._code_signature = original

    assert result.classification is ChangeClass.REPOINTED, "evidence beats heuristic"
    assert result.is_semantic is True
    assert any("disagreement is a bug in Vouch" in n for n in result.notes), \
        "and when they disagree it says so, rather than picking a winner quietly"


# ======================================================================================
# 4. it must not invent a change that is not there
# ======================================================================================
#
# The other direction. A module that cries wolf on a reformatted comment gets ignored on the day it
# matters, and every mutation below is one a code generator makes for free.

REAL_SOURCES = ["p1_template_b.js", "p2_template_b.js", "p3_template_a.js", "ms_template_b.js",
                "parse_template_a.js"]


def _cosmetic_mutations(src: str) -> list[tuple[str, str]]:
    return [
        ("every comment stripped", re.sub(r"^\s*//.*$", "", src, flags=re.M)),
        ("a comment added", "// a note about nothing in particular\n" + src),
        ("a comment mentioning a selector added",
         "// TODO: should this read .price-ship instead?\n" + src),
        ("indentation doubled",
         "\n".join("  " + l if l.strip() else l for l in src.splitlines())),
        ("blank lines everywhere", src.replace("\n", "\n\n")),
        ("trailing whitespace on every line", "\n".join(l + "   " for l in src.splitlines())),
        ("CRLF line endings", src.replace("\n", "\r\n")),
    ]


@pytest.mark.parametrize("name", REAL_SOURCES)
def test_cosmetic_edits_to_real_parser_source_never_surface_as_semantic(name):
    """Comments, blank lines, indentation, trailing space, line endings. None of it is a change.

    Note the third mutation: a comment that NAMES a selector the code does not read. The literal
    scanner runs before any structural matching precisely so that a selector mentioned in prose can
    never be read as code, and this is that guarantee stated as a test rather than as a docstring.
    """
    src = source(name)
    for label, mutated in _cosmetic_mutations(src):
        result = diff_templates(wrap(src, mutated))
        assert result.is_semantic is False, f"{name}: {label} was reported as semantic"
        assert result.is_cosmetic is True, f"{name}: {label} was not recognised as cosmetic"
        assert result.field_changes == (), f"{name}: {label} produced field changes"
        assert result.bullets() == [], f"{name}: {label} said something to the operator"


def test_renaming_every_local_variable_changes_nothing():
    """Resolution follows values, not names. P1's real source, with all nine locals renamed."""
    src = source("p1_template_b.js")
    renamed = src
    for old, new in (("priceCurrentText", "pc"), ("priceShipText", "ps"), ("priceWasText", "pw"),
                     ("priceValue", "pv"), ("shippingValue", "sv"), ("originalPriceValue", "opv"),
                     ("ratingText", "rt"), ("stockElement", "se"), ("parsePrice", "pp")):
        renamed = re.sub(r"\b" + old + r"\b", new, renamed)
    assert renamed != src

    result = diff_templates(wrap(src, renamed))

    assert result.classification is ChangeClass.LOGIC_ONLY, "the text changed; the field map did not"
    assert result.is_semantic is False
    assert result.code_lines_changed > 0, "and it is honest that lines of code moved"


def test_reordering_independent_statements_changes_nothing():
    """Three `let`s that do not depend on each other, shuffled."""
    src = source("p1_template_b.js")
    lines = src.splitlines()
    i = next(k for k, l in enumerate(lines) if "priceCurrentText =" in l)
    shuffled = "\n".join(lines[:i] + [lines[i + 2], lines[i + 1], lines[i]] + lines[i + 3:])

    result = diff_templates(wrap(src, shuffled))

    assert result.is_semantic is False
    assert result.classification is ChangeClass.LOGIC_ONLY


def test_moving_an_extraction_and_reordering_the_record_keys_changes_nothing():
    """Where a field is computed, and in what order the record lists it, are not properties of it."""
    src = source("ms_template_b.js")
    moved = src.replace("  // Extract name\n  let name = $item.find('.item-title').text_sane();\n\n", "")
    moved = moved.replace("  return {", "  let name = $item.find('.item-title').text_sane();\n  return {")
    reordered = moved.replace("    name,\n    price,\n    original_price,\n    shipping,\n",
                              "    shipping,\n    original_price,\n    price,\n    name,\n")
    assert reordered != src

    result = diff_templates(wrap(src, reordered))

    assert result.is_semantic is False
    assert result.field_changes == ()


def test_a_selector_only_ever_mentioned_in_a_string_is_not_read_as_code():
    """Layer 1, on its own terms: prose and data are not code, whatever they contain."""
    src = source("ms_template_b.js")
    noisy = src.replace(
        "let products =",
        "let unused = ['.price-was', '.price-current', `.cost-${x}`];\n"
        "let msg = 'switching price to .price-ship';\nlet products =")

    result = diff_templates(wrap(src, noisy))

    assert result.is_semantic is False, "a selector in a string array is not a read"
    assert result.classification is ChangeClass.LOGIC_ONLY


def test_one_genuinely_changed_selector_still_fires():
    """The control for the whole section. Insensitivity is only a virtue if sensitivity survives."""
    src = source("ms_template_b.js")

    result = diff_templates(wrap(src, src.replace(".item-title", ".product-name")))

    assert result.is_semantic is True
    assert [(c.field, c.before, c.after) for c in result.field_changes] == \
        [("name", (".item-title",), (".product-name",))]


# ======================================================================================
# 5. the discrimination question: P1 vs the misleading heals
# ======================================================================================

def test_the_conditional_split_between_p1_and_the_misleading_heals_is_recorded_not_used():
    """The measurement, written down so the next person does not have to re-derive it.

    P1 is CORRECT and its repoint is conditional and retaining. Both misleading heals are WRONG and
    both are unconditional. That is 1/1 against 0/2 and it looks like a discriminator.

    Nothing reads it. This test asserts the observation AND asserts that the module exposes no score,
    severity or verdict built on top of it - see the next two tests for why, and the module docstring
    for the argument in full.
    """
    p1 = diff_templates(captured("heal_p1.json"))
    shipping = diff_templates(captured("heal_mislead_shipping.json"))
    crossed = diff_templates(captured("heal_mislead_crossed.json"))

    def conditional_repoints(result):
        return {c.field for c in result.field_changes if c.conditional_now}

    assert conditional_repoints(p1) == {"price"}, "the correct heal branched on the label text"
    assert conditional_repoints(shipping) == set()
    assert conditional_repoints(crossed) == set()

    # And every one of the three still escalates identically. The split changes the SENTENCE, not
    # the decision, which is the whole of the policy.
    assert all(r.is_semantic for r in (p1, shipping, crossed))


def test_a_wrong_heal_can_be_conditional_too_so_the_split_cannot_be_promoted_to_a_rule():
    """The constructive refutation, which is what settles it - not the sample size.

    Hand-built, and labelled as such: this is not a captured heal. It is P1's exact idiom - branch on
    a page fact, keep the old element on the other arm - applied to the misleading instruction "on a
    sale item the price is the delivery charge". It is wrong on every discounted product, and it
    reports `conditional_now=True` and `retained=True`, exactly like the correct heal.

    That is possible because the difference between the two is a fact about the MARKUP and the markup
    is not in the diff. A conditional says "I believe this page is inconsistent"; whether the belief
    is true is not something the source can be asked. An agreeable healer writes a confident
    conditional as readily as a confident assignment, and P1 proves it writes conditionals unprompted.
    """
    before = """
    let products = $('.grid .item').toArray().map(item => {
      let $item = $(item);
      let cur = $item.find('.price-current').text_sane();
      let ship = $item.find('.price-ship').text_sane();
      let was = $item.find('.price-was').text_sane();
      let price;
      price = parsePrice(cur);
      return { name: $item.find('.item-title').text_sane(), price: price,
               original_price: parsePrice(was), shipping: parsePrice(ship) };
    });
    return { products };
    """
    # ...and the "heal": on a sale item, read the delivery charge instead. Confidently wrong.
    after = before.replace(
        "      price = parsePrice(cur);",
        "      if (was) {\n"
        "        price = parsePrice(ship);   // sale price is the delivery charge (per user request)\n"
        "      } else {\n"
        "        price = parsePrice(cur);\n"
        "      }")

    result = diff_templates(wrap(before, after))
    price = next(c for c in result.field_changes if c.field == "price")

    assert price.conditional_now is True, "the wrong heal branches, just as the correct one did"
    assert price.retained is True, "and keeps its old element, just as the correct one did"
    assert price.borrowed_from == ("shipping",)
    assert result.has_swap is False
    # Structurally it is P1. Semantically it is the shipping heal. The source cannot tell them apart,
    # and this is the assertion that stops anyone wiring `conditional_now` to a decision later.
    p1_price = next(c for c in diff_templates(captured("heal_p1.json")).field_changes
                    if c.field == "price")
    assert (price.conditional_now, price.retained, price.borrowed_from) == \
           (p1_price.conditional_now, p1_price.retained, p1_price.borrowed_from)


def test_the_same_source_diff_is_a_correct_heal_on_one_page_and_a_wrong_one_on_another():
    """The limit stated as an identity: the module's output is a function of the source alone.

    FINDINGS.md says the P1 page swapped price and delivery in tile 1. Had it swapped them in ALL
    thirty, the CORRECT heal would be the unconditional `price := .price-ship` - which is, character
    for character in the part that matters, the heal that was WRONG on the unswapped page. One diff,
    two truths, decided entirely by markup the diff does not contain.

    So: no source-only discriminator exists, and this test is the reason the module says so in its
    docstring rather than shipping a heuristic that fits three examples.
    """
    unswapped_page_heal = diff_templates(captured("heal_mislead_shipping.json"))

    # The same repoint, written out as it would be for a page that really had swapped every tile.
    before = """
    let products = $('.item').toArray().map(item => {
      let $item = $(item);
      return { name: $item.find('.item-title').text_sane(),
               price: $item.find('.price-current').text_sane(),
               shipping: $item.find('.price-ship').text_sane() };
    });
    return { products };
    """
    swapped_page_heal = diff_templates(wrap(
        before, before.replace("$item.find('.price-current').text_sane(),\n               shipping",
                               "$item.find('.price-ship').text_sane(),\n               shipping")))

    a = next(c for c in unswapped_page_heal.field_changes if c.field == "price")
    b = next(c for c in swapped_page_heal.field_changes if c.field == "price")
    assert (a.before, a.after, a.borrowed_from, a.conditional_now, a.retained) == \
           (b.before, b.after, b.borrowed_from, b.conditional_now, b.retained)
    assert unswapped_page_heal.is_semantic is swapped_page_heal.is_semantic is True


# ======================================================================================
# 6. the integration contract - escalate and explain, never decide
# ======================================================================================

def test_the_module_cannot_reject_a_heal_because_it_has_nothing_to_reject_with():
    """P1 is the reason, and the guarantee is structural rather than a matter of thresholds.

    Nothing here imports `CheckResult`, `Severity` or `Verdict`, and nothing here produces a score,
    a decision or a `passed` flag. There is therefore no value this module can return that
    `verdict.decide` would read as a failure - the strongest form the requirement can take, because
    it cannot be undone by someone tuning a number.

    The alternative was a CheckResult in checks.py. `decide` FAILs on any CRITICAL and REVIEWs on any
    HIGH, and `_score` charges 10 for a MEDIUM: a MEDIUM repoint finding could not reject a heal
    alone, but stacked on other findings it could be the ten points that carries one from REVIEW to
    FAIL - and P1, which reports has_swap=True and was correct, is the heal it would carry.
    """
    exported = {name for name in dir(td) if not name.startswith("_")}

    assert not exported & {"CheckResult", "Severity", "Verdict", "decide", "run_all_checks"}
    for payload, *_ in MEASURED:
        result = diff_templates(captured(payload))
        rendered = result.to_dict()
        assert set(rendered) & {"severity", "passed", "decision", "confidence", "score"} == set()
        assert not hasattr(result, "severity") and not hasattr(result, "decision")


def test_the_orchestrators_two_reads_of_a_diff_stay_in_step():
    """The exact pair `orchestrator` branches on, held together at the source.

    `_publishable` gates the extra page load on `not diff.is_semantic`; `_with_source_note` and
    `service._evidence` both gate the operator-facing sentence on `is_semantic` AND a non-empty
    `summary`. If a diff could ever escalate while carrying an empty summary, the loop would spend a
    page load and print nothing about why.
    """
    for payload, *_ in MEASURED:
        result = diff_templates(captured(payload))
        if result.is_semantic:
            assert result.summary, f"{payload} escalates with nothing to say"
    for raw in [None, {}, {"template_a": {"steps": []}, "template_b": {"steps": []}},
                {"template_a": {"steps": [{"parse_code": "x"}]}}]:
        result = diff_templates(raw)
        assert result.summary
        assert result.is_semantic == (result.has_demonstrated_repoint or result.could_not_read)


def test_a_mock_mode_heal_carries_no_diff_and_costs_no_extra_page():
    """MOCK_MODE never asks for `--legacy-output`, so `raw_diff` is None on every demo heal.

    Pinned here as well as in test_orchestrator.py because it is the one case where returning
    `is_semantic=False` on ignorance is CORRECT, and a future tightening of the honesty rule must
    trip over it deliberately rather than quietly make the demo cost a page load per heal.
    """
    result = diff_templates(None)

    assert result.status is ExtractionStatus.NO_DIFF
    assert result.is_semantic is False
    assert result.could_not_read is False


def test_to_dict_carries_every_claim_the_brief_renders():
    """`service._evidence` reads `semantic` and `summary` off this dict; the rest is for the UI."""
    rendered = diff_templates(captured("heal_mislead_shipping.json")).to_dict()

    assert json.loads(json.dumps(rendered)) == rendered, "must survive the wire unchanged"
    assert rendered["semantic"] is True
    assert rendered["demonstrated_repoint"] is True
    assert rendered["could_not_read"] is False
    assert rendered["cross_field_repoint"] is True
    assert rendered["collisions"] == [["price", "shipping"]]
    assert "the element 'shipping' read before" in rendered["summary"]
    assert rendered["field_changes"][0]["text"].startswith("price: '.price-current' -> '.price-ship'")


# ======================================================================================
# 7. parse_template on its own
# ======================================================================================

def test_parse_template_answers_what_does_this_collector_read():
    """It is public because it is useful alone - the question an operator asks about a collector
    they did not write that has started producing something odd."""
    parsed = parse_template(source("p1_template_b.js"))

    assert parsed.ok
    assert parsed.root_selector == ".grid .item"
    fields = parsed.by_name()
    assert fields["price"].conditional is True
    assert fields["price"].keys == (".price-current", ".price-ship")
    assert fields["name"].keys == (".item-title",)
    assert parsed.vocabulary()[".price-current"] == {"price", "shipping"}


@pytest.mark.parametrize("bad", [None, "", "   ", 7, [], {}])
def test_parse_template_declines_rather_than_returning_an_empty_map(bad):
    """An empty field map and "there was no source" must never render the same.

    An empty `fields` tuple with status OK would compare equal to any other empty map, which is how
    "we read nothing" becomes "nothing changed" one level up.
    """
    parsed = parse_template(bad)

    assert parsed.status is ExtractionStatus.NO_PARSE_CODE
    assert parsed.ok is False
    assert parsed.fields == ()


def test_a_money_constructors_currency_argument_is_not_attributed_to_the_field():
    """`new Money(value, currency)` - only the first argument says where the VALUE came from.

    Unioning the currency argument in would attribute every money field to whichever element the
    currency symbol was scraped from, and then a heal that changed only the currency lookup would
    read as three fields repointing at once.

    Written in the idiom the generator actually emits: both arguments are locals, which is the form
    in all 30 `new Money(...)` calls across the captured templates. See the next test for the form
    it does not emit, where the defence does not hold.
    """
    src = """
    let products = $('.item').toArray().map(item => {
      let $item = $(item);
      let priceValue = $item.find('.price-current').text_sane();
      let currency = $item.find('.currency-badge').text_sane();
      return {
        name: $item.find('.item-title').text_sane(),
        price: new Money(priceValue, currency)
      };
    });
    return { products };
    """
    parsed = parse_template(src)

    assert parsed.by_name()["price"].keys == (".price-current",)
    result = diff_templates(wrap(src, src.replace(".currency-badge", ".ccy")))
    assert result.is_semantic is False, "the currency lookup moved; no field's value did"


def test_an_inline_constructor_argument_over_attributes_and_that_is_a_known_limitation():
    """FOUND, NOT FIXED. Pinned so it is a documented limit rather than a surprise.

    `_resolve_expression` tries "a literal `.find('sel')` anywhere in this expression IS the answer"
    BEFORE it tries the constructor rule, so the first-argument-only defence only bites when the
    arguments are locals. Write the two `.find()` calls inline and both are attributed to the field.

    Left alone deliberately. The form does not occur in any of the six captured heals - all 30
    `new Money(...)` calls pass locals - and reordering the resolution rules would change how every
    real template resolves in order to fix a shape none of them use. The cost of the gap is a false
    POSITIVE: a heal that moved only the currency lookup reads as every money field repointing,
    which buys a page load and prints a sentence that overstates what happened. The cost of the
    reorder is unmeasured behaviour change on the payloads the module is calibrated against. If the
    generator's idiom ever changes, this test is where to start.
    """
    src = """
    let products = $('.item').toArray().map(item => {
      let $item = $(item);
      return {
        name: $item.find('.item-title').text_sane(),
        price: new Money($item.find('.price-current').text_sane(),
                         $item.find('.currency-badge').text_sane())
      };
    });
    return { products };
    """
    parsed = parse_template(src)

    assert parsed.by_name()["price"].keys == (".currency-badge", ".price-current"), \
        "the currency element is attributed to price - this is the limitation, not the intent"
    result = diff_templates(wrap(src, src.replace(".currency-badge", ".ccy")))
    assert result.is_semantic is True, "and it over-reports, which costs a page load, not a heal"
