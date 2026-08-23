"""
Read what a heal INTENDS, not only what it produced.

`scraper heal --legacy-output` returns `diff.template_a` and `diff.template_b`: the collector as it
stands and the collector the healer proposes, each carrying the real JavaScript parser as readable
source under `steps[0].parse_code`. Vouch throws that away today and judges the heal purely on the
rows it emitted. This module reads the source instead.

Why bother, when we already have value-level checks
---------------------------------------------------
The 2026-08-23 study (docs/research/FINDINGS.md) measured the failure mode this exists for. Bright
Data's healer is *good at reading pages* - three separate layout attacks failed to fool it - and
*bad at doubting operators*. Told "the correct price is the delivery charge", it dutifully emitted:

    - // Extract current price
    - let price_text = $item.find('.price-current').text_sane();
    + // Extract shipping cost as price (per user request)
    + let shipping_text = $item.find('.price-ship').text_sane();

In the VALUES that error needed all 30 rows to see: on the 2-row preview the approval gate actually
shows, the distance from the previewed `price` to the baseline `shipping` distribution was 0.50,
exactly double `check_column_swap`'s threshold, and the bad heal scored PASS 100/100. In the SOURCE
it is one line, legible before a single extra credit is spent.

So this is not a replacement for the distributional battery - it is the piece of evidence that is
available when the battery is structurally blind, which is precisely the swap-class errors the
battery exists to catch. Different modality, same failure, no marginal cost.

What "evidence" means here
--------------------------
The output is a field-level map of *which element each output field reads from*, on both sides, and
the differences between those maps:

    price: '.price-current' -> '.price-ship'   (the element 'shipping' read before)

That statement is actionable by a human in about two seconds. It is also the only claim strong
enough to be worth making, so it is the only one this module tries to make.

On parsing JavaScript with regular expressions
----------------------------------------------
We are not writing a JavaScript parser and this module must never pretend otherwise. Its output
feeds a human deciding whether to commit a scraper to production; a plausible-looking WRONG finding
is far more damaging than a missing one, because a wrong finding is indistinguishable from a right
one at the point of use and it burns the operator's trust in every finding after it.

The defence is three-layered:

  1. A small literal-aware scanner (`_blank_literals`) runs first and neutralises comments, strings,
     template literals and regex literals. All structural pattern matching then happens against that
     blanked text, so a selector mentioned in a comment or embedded in a string can never be read as
     code. If the scanner ends in an unterminated state, we return NOTHING for the whole template.
  2. Resolution follows a deliberately narrow set of syntactic shapes (see `_resolve_expression`).
     Anything outside them - a dynamic `.find(variable)`, a template-literal selector, a return
     object we cannot identify - yields an explicit "unresolved" marker for that field.
  3. A field that is unresolved on EITHER side is never reported as changed. It is listed under
     `unresolved_fields` with a reason, so the absence of evidence is itself visible.

The honest characterisation of the extractor: it recognises the idiom Bright Data's code generator
actually emits, and it declines on everything else.

Deliberate non-coupling
-----------------------
Nothing here imports `CheckResult`, `Severity` or `Verdict`. The guardian's result types are being
refactored concurrently, and more importantly this module answers a *different question* from a
check: a check asks "are these values wrong", this asks "what did the heal change". Those want
different shapes. Integration is a thin adapter someone else writes over `TemplateDiff.to_dict()`;
see the note at the bottom of this docstring for the recommended policy.

Recommended integration policy (argued, not merely stated)
----------------------------------------------------------
Selector evidence should be a strong ESCALATOR and never, on its own, a rejection:

  - `has_cross_field_repoint` is the highest-value signal in here - a field now reading the element
    another field read before is the literal signature of the two heals that broke in the study. It
    should be able to push PASS -> REVIEW by itself, because REVIEW costs a human glance and this
    evidence is exactly a request for one.
  - It should NOT be able to produce FAIL alone. A cross-field repoint is a legitimate fix whenever
    the PAGE was the thing that swapped - and that page exists; it is P1 in the study, where the
    correct heal genuinely had to start reading price out of `.price-ship`. Failing on the source
    alone would reject the correct heal for the same reason it rejects the incorrect one.
  - Combined with a value-level swap finding it is close to proof, and the pair should read as one
    finding in the brief rather than two, the way `verdict._swap_pairs` already collapses
    double-reported COLUMN_SWAPs.
  - COSMETIC and LOGIC_ONLY must stay silent. The healthy-page probe in the study changed only
    comments and added a defensive decimal guard; surfacing that as a change would teach operators
    that this evidence is noise, and they would then ignore the one time it is not.

Usage
-----
    from app.guardian.template_diff import diff_templates

    result = diff_templates(heal_response["diff"])      # or the whole heal response
    if result.is_semantic:
        for line in result.bullets():
            print(line)
    # price: '.price-current' -> '.price-ship' (previously read by 'shipping')

Pure stdlib, no network, no credits.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Iterable, Optional


# ======================================================================================
# Public vocabulary
# ======================================================================================

class ChangeClass(str, Enum):
    """How much the heal actually changed, from an operator's point of view.

    The ordering matters: everything below REPOINTED is a change no one needs to be woken up for,
    and conflating them is how a warning channel dies.
    """

    IDENTICAL = "identical"        # byte-for-byte the same parser
    COSMETIC = "cosmetic"          # only comments / blank lines / whitespace moved
    LOGIC_ONLY = "logic_only"      # real code changed, but no field reads a different element
    REPOINTED = "repointed"        # at least one field now reads a DIFFERENT element - the one to act on
    UNKNOWN = "unknown"            # we could not read one or both sides; deliberately makes no claim


class ExtractionStatus(str, Enum):
    """Why we do or do not have a field map. `OK` is the only value that carries claims."""

    OK = "ok"
    NO_DIFF = "no_diff"                    # raw_diff absent or not shaped like a legacy diff
    NO_PARSE_CODE = "no_parse_code"        # a side had no readable parse_code
    UNREADABLE_SOURCE = "unreadable_source"  # scanner hit an unterminated literal - refuse to guess
    UNRECOGNISED_SHAPE = "unrecognised_shape"  # no identifiable record-return object


@dataclass(frozen=True)
class SelectorRef:
    """One DOM element reference as it literally appears in the parser source.

    `positional` carries `eq(1)` / `first()` / `last()` when the template disambiguates by ORDER
    rather than by class. That is not decoration: P2 in the study was a page with no labels at all,
    where the healer's only available answer was `.money.eq(1)`, and "the second `.money` span"
    versus "the first" is the entire difference between the price and the shipping cost. Dropping
    the modifier would render two genuinely different reads identical.
    """

    selector: str
    positional: Optional[str] = None

    def render(self) -> str:
        return f"{self.selector}:{self.positional}" if self.positional else self.selector

    def __str__(self) -> str:                                    # pragma: no cover - convenience
        return self.render()


@dataclass(frozen=True)
class FieldSource:
    """Where one output field's value comes from, or an honest account of why we do not know.

    `selectors` holds every element the field's value can be traced back to. More than one means the
    template BRANCHES - P1's correct heal reads price from `.price-current` or `.price-ship`
    depending on the label text - which is a real and reportable property, not an extraction
    failure. `resolved=False` is the extraction failure, and it suppresses all change claims about
    this field.
    """

    name: str
    selectors: tuple[SelectorRef, ...] = ()
    resolved: bool = True
    reason: Optional[str] = None          # populated iff resolved is False
    conditional: bool = False             # value depends on a branch; may also fall through to a constant
    has_constant_branch: bool = False     # at least one branch pins the field to a literal (often null)

    @property
    def keys(self) -> tuple[str, ...]:
        """Comparable rendering - what we actually diff on."""
        return tuple(sorted(s.render() for s in self.selectors))

    def describe(self) -> str:
        if not self.resolved:
            return f"unresolved ({self.reason})"
        if not self.selectors:
            return "no element (constant)"
        rendered = " or ".join(f"'{s.render()}'" for s in self.selectors)
        return rendered + (" (conditional)" if self.conditional else "")


@dataclass(frozen=True)
class ParsedTemplate:
    """The readable half of one side of the diff."""

    status: ExtractionStatus
    root_selector: Optional[str] = None
    fields: tuple[FieldSource, ...] = ()
    notes: tuple[str, ...] = ()
    source: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ExtractionStatus.OK

    def by_name(self) -> dict[str, FieldSource]:
        return {f.name: f for f in self.fields}

    def vocabulary(self) -> dict[str, set[str]]:
        """selector -> the set of fields that read it. Used to detect cross-field borrowing."""
        out: dict[str, set[str]] = {}
        for f in self.fields:
            if not f.resolved:
                continue
            for key in f.keys:
                out.setdefault(key, set()).add(f.name)
        return out


@dataclass(frozen=True)
class FieldChange:
    """One field reads something different than it did. The unit of evidence a human acts on."""

    field: str
    kind: str                                  # "repointed" | "added" | "removed"
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    borrowed_from: tuple[str, ...] = ()        # fields that read the NEW element on side A
    conditional_now: bool = False
    retained: bool = False                     # still reads at least one of its OLD elements

    def describe(self) -> str:
        if self.kind == "added":
            return f"{self.field}: new field, reads {_join(self.after)}"
        if self.kind == "removed":
            return f"{self.field}: field dropped (read {_join(self.before)})"
        if self.retained:
            # It kept its old element and gained another. Saying "A -> A or B" reads as a move and
            # it is not one; the field WIDENED, which is a materially different thing to review.
            gained = _join(k for k in self.after if k not in self.before)
            line = f"{self.field}: still reads {_join(self.before)}, now ALSO reads {gained}"
        else:
            line = f"{self.field}: {_join(self.before)} -> {_join(self.after)}"
        if self.borrowed_from:
            others = ", ".join(f"'{n}'" for n in self.borrowed_from)
            line += f" (the element {others} read before)"
        if self.conditional_now:
            line += " [branches on page content]"
        return line


@dataclass
class TemplateDiff:
    """The whole finding. Plain dataclass on purpose - see the module docstring on non-coupling."""

    status: ExtractionStatus
    classification: ChangeClass
    summary: str
    field_changes: tuple[FieldChange, ...] = ()
    swapped_pairs: tuple[tuple[str, str], ...] = ()
    collisions: tuple[tuple[str, str], ...] = ()
    root_before: Optional[str] = None
    root_after: Optional[str] = None
    unresolved_fields: tuple[tuple[str, str], ...] = ()   # (field, reason)
    comment_lines_changed: int = 0
    code_lines_changed: int = 0
    notes: tuple[str, ...] = dc_field(default_factory=tuple)
    template_a: Optional[ParsedTemplate] = None
    template_b: Optional[ParsedTemplate] = None

    # -- predicates the integrator will branch on -------------------------------------
    @property
    def is_semantic(self) -> bool:
        """At least one field demonstrably reads a different element. The actionable case."""
        return self.classification is ChangeClass.REPOINTED

    @property
    def is_cosmetic(self) -> bool:
        """Nothing but comments and whitespace moved. Must never surface as a warning."""
        return self.classification in (ChangeClass.IDENTICAL, ChangeClass.COSMETIC)

    @property
    def has_cross_field_repoint(self) -> bool:
        """A field now reads an element that a DIFFERENT field read before the heal.

        This is the signature of both heals that broke in the study, and the one signal here worth
        letting move a decision. Note what it excludes: P3 renamed every class on the page and every
        field followed, but no field took over another field's element, so this stays False.
        """
        return any(c.borrowed_from for c in self.field_changes)

    @property
    def has_swap(self) -> bool:
        return bool(self.swapped_pairs)

    @property
    def root_changed(self) -> bool:
        return self.root_before != self.root_after

    def bullets(self) -> list[str]:
        """Operator-facing lines. Empty when we have nothing worth saying, which is most of the time."""
        if self.classification in (ChangeClass.IDENTICAL, ChangeClass.COSMETIC, ChangeClass.UNKNOWN):
            return []
        out: list[str] = []
        if self.root_changed:
            out.append(f"record selector: {_q(self.root_before)} -> {_q(self.root_after)}")
        out.extend(c.describe() for c in self.field_changes)
        for a, b in self.swapped_pairs:
            # Deliberately neutral. A page whose markup swapped two values REQUIRES a heal that
            # crosses them - that is P1 in the study, and it was the correct answer. The source
            # cannot tell you which of the two happened; only the full-page values can.
            out.append(f"'{a}' and '{b}' now read each other's previous elements - either the page "
                       f"swapped them or the heal did")
        for a, b in self.collisions:
            out.append(f"'{a}' and '{b}' now read the SAME element")
        out.extend(self.notes)
        if self.unresolved_fields:
            names = ", ".join(n for n, _ in self.unresolved_fields)
            out.append(f"not checked (source shape unfamiliar): {names}")
        return out

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe. Shaped to drop straight into a CheckResult's `evidence` without translation."""
        return {
            "status": self.status.value,
            "classification": self.classification.value,
            "summary": self.summary,
            "semantic": self.is_semantic,
            "cosmetic": self.is_cosmetic,
            "cross_field_repoint": self.has_cross_field_repoint,
            "swapped_pairs": [list(p) for p in self.swapped_pairs],
            "collisions": [list(p) for p in self.collisions],
            "root_before": self.root_before,
            "root_after": self.root_after,
            "field_changes": [
                {
                    "field": c.field,
                    "kind": c.kind,
                    "before": list(c.before),
                    "after": list(c.after),
                    "borrowed_from": list(c.borrowed_from),
                    "conditional": c.conditional_now,
                    "text": c.describe(),
                }
                for c in self.field_changes
            ],
            "unresolved_fields": [list(u) for u in self.unresolved_fields],
            "comment_lines_changed": self.comment_lines_changed,
            "code_lines_changed": self.code_lines_changed,
            "notes": list(self.notes),
        }


def _q(v: Optional[str]) -> str:
    return f"'{v}'" if v else "(none)"


def _join(keys: Iterable[str]) -> str:
    keys = list(keys)
    if not keys:
        return "nothing"
    return " or ".join(f"'{k}'" for k in keys)


# ======================================================================================
# Layer 1 - literal-aware blanking
# ======================================================================================
#
# Everything structural is matched against the OUTPUT of this function, never against raw source.
# The output is the same length as the input and shares every index with it, so a pattern matched on
# the blanked text can be sliced out of the original to recover the literal it stands for.
#
#   comments            -> spaces (newlines preserved, so line numbers survive)
#   string contents     -> NUL, delimiters kept  ('abc'  ->  '\0\0\0')
#   template literals   -> NUL, backticks kept
#   regex literals      -> NUL, slashes kept
#
# Keeping the delimiters is what makes `.find('<NUL>*')` a reliable structural pattern while
# `.find(someVariable)` and `.find(`a${b}`)` deliberately fail to match it.

_NUL = "\x00"

# A '/' begins a regex literal rather than a division only in prefix position. This is the standard
# lexer heuristic: look at the previous significant character. It is not complete JavaScript (no
# heuristic on a raw character stream can be), but a misread here fails SAFE - the scanner either
# terminates and yields a slightly wrong blanking of a region that contains no selector, or it fails
# to terminate and we discard the whole template rather than report from it.
_REGEX_PREFIX_CHARS = set("(,=:[!&|?{};+-*%^~<>\n")


def _blank_literals(src: str) -> Optional[str]:
    """Return `src` with comments and literal contents neutralised, or None if it is unreadable.

    None is a first-class outcome. An unterminated string or block comment means our model of the
    file is wrong somewhere, and every downstream claim would be built on that wrongness - so we
    throw the whole template away instead. Returning a partial parse here would be the exact
    'silent wrong evidence' failure this module is written to avoid.
    """
    n = len(src)
    out = list(src)
    i = 0
    prev = "\n"           # start-of-input counts as prefix position
    while i < n:
        c = src[i]

        # line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue

        # block comment
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j == -1:
                return None                      # unterminated - refuse the template
            for k in range(i, j + 2):
                if out[k] != "\n":
                    out[k] = " "
            i = j + 2
            continue

        # string literal
        if c in "'\"":
            j = _scan_quoted(src, i, c, allow_newline=False)
            if j is None:
                return None
            for k in range(i + 1, j):
                out[k] = _NUL
            prev = c
            i = j + 1
            continue

        # template literal - blanked wholesale, including any ${...} inside it. We never try to
        # evaluate one, so a template-literal selector simply becomes unresolvable, which is right.
        if c == "`":
            j = _scan_quoted(src, i, "`", allow_newline=True)
            if j is None:
                return None
            for k in range(i + 1, j):
                if out[k] != "\n":
                    out[k] = _NUL
            prev = "`"
            i = j + 1
            continue

        # regex literal
        if c == "/" and prev in _REGEX_PREFIX_CHARS:
            j = _scan_regex(src, i)
            if j is not None:
                for k in range(i + 1, j):
                    out[k] = _NUL
                prev = "/"
                i = j + 1
                continue
            # not a terminating regex on this line - fall through and treat '/' as division

        if not c.isspace():
            prev = c
        elif c == "\n":
            prev = "\n"
        i += 1
    return "".join(out)


def _scan_quoted(src: str, start: int, quote: str, allow_newline: bool) -> Optional[int]:
    """Index of the closing quote, or None if the literal never closes."""
    i = start + 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i
        if c == "\n" and not allow_newline:
            return None
        i += 1
    return None


def _scan_regex(src: str, start: int) -> Optional[int]:
    """Index of the closing '/' of a regex literal, or None if this '/' is not one.

    A JavaScript regex literal cannot contain an unescaped newline, so hitting one is proof we
    misjudged prefix position and the character was division after all.
    """
    i = start + 1
    n = len(src)
    in_class = False
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            return None
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            return i
        i += 1
    return None


# ======================================================================================
# Layer 2 - structural extraction
# ======================================================================================
#
# Every pattern below is matched against blanked text. `_NUL*` in a pattern means "a string literal
# whose contents we will slice out of the original by index".

_STR = r"(['\"])(\x00*)\1"

_ROOT_RE = re.compile(r"(?<![\w$.])\$\(\s*" + _STR + r"\s*\)")
_FIND_LIT_RE = re.compile(r"\.find\(\s*" + _STR + r"\s*\)")
_FIND_ANY_RE = re.compile(r"\.find\(")
_DOLLAR_ANY_RE = re.compile(r"(?<![\w$.])\$\(")
_POSITIONAL_RE = re.compile(r"\A\s*\.(eq\(\s*\d+\s*\)|first\(\)|last\(\))")
_RETURN_OBJ_RE = re.compile(r"\breturn\s*\{")

# An assignment we are willing to follow. Requires a bare identifier on the left - we deliberately do
# not follow property assignments (`obj.x = ...`), because resolving them correctly needs aliasing
# analysis and getting it wrong would mean attributing a selector to the wrong field.
_ASSIGN_RE = re.compile(r"(?<![\w$.])(?:(?:let|const|var)\s+)?([A-Za-z_$][\w$]*)\s*=(?![=>])")

# Identifiers in value position: not a property name (no leading dot) and not a callee (no trailing
# paren). Only those that appear in the assignment index are ever followed, so this list only has to
# exclude things that could otherwise shadow a real local.
_IDENT_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?!\s*\()")
_RESERVED = {
    "null", "true", "false", "undefined", "NaN", "new", "return", "typeof", "instanceof",
    "let", "const", "var", "if", "else", "for", "while", "function", "this", "in", "of",
    "delete", "void", "await", "yield", "class", "try", "catch", "throw", "switch", "case",
}
_CONSTANT_RE = re.compile(
    r"\A\s*(?:null|undefined|true|false|-?\d+(?:\.\d+)?|'\x00*'|\"\x00*\")\s*\Z")

_NEW_CALL_RE = re.compile(r"(?<![\w$.])new\s+[A-Za-z_$][\w$]*\s*\(")

_MAX_DEPTH = 10          # a resolution chain deeper than this is not an idiom we recognise


class _Blanked:
    """A source string paired with its blanked twin, sliced in lockstep.

    Every index into one is a valid index into the other. Structural searching happens on `.blank`;
    literal text is always read from `.src`.
    """

    __slots__ = ("src", "blank")

    def __init__(self, src: str, blank: str) -> None:
        self.src = src
        self.blank = blank

    def sub(self, start: int, end: int) -> "_Blanked":
        return _Blanked(self.src[start:end], self.blank[start:end])


def _find_selectors(code: _Blanked) -> tuple[list[SelectorRef], bool]:
    """All literal element references in an expression, plus whether any DYNAMIC one was present.

    The second return value is the important one. `.find(someVar)` and ``.find(`a${b}`)`` are
    perfectly legal and completely opaque to us; if one appears we must not report the literal
    selectors alongside it as if they were the whole story, because the field's real source might be
    the one we cannot see.
    """
    refs: list[SelectorRef] = []
    literal_spans = 0

    for m in _ROOT_RE.finditer(code.blank):
        refs.append(SelectorRef(code.src[m.start(2):m.end(2)]))
        literal_spans += 1
    for m in _FIND_LIT_RE.finditer(code.blank):
        selector = code.src[m.start(2):m.end(2)]
        tail = _POSITIONAL_RE.match(code.blank[m.end():])
        refs.append(SelectorRef(selector, code.src[m.end() + tail.start(1):m.end() + tail.end(1)] if tail else None))
        literal_spans += 1

    total_calls = len(_FIND_ANY_RE.findall(code.blank)) + len(_DOLLAR_ANY_RE.findall(code.blank))
    return refs, total_calls > literal_spans


def _split_top_level(code: _Blanked, sep: str) -> list[tuple[int, int]]:
    """Spans between top-level occurrences of a single-character separator."""
    spans: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for i, c in enumerate(code.blank):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            spans.append((start, i))
            start = i + 1
    spans.append((start, len(code.blank)))
    return spans


def _match_brace(blank: str, open_idx: int) -> Optional[int]:
    depth = 0
    for i in range(open_idx, len(blank)):
        c = blank[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _root_selector(code: _Blanked) -> tuple[Optional[str], list[str]]:
    """The record selector - the `$('...')` the whole collector maps over.

    Multiple distinct literal `$('...')` calls make "the" root ambiguous, so we take the first and
    say so in a note rather than silently picking one.
    """
    found: list[str] = []
    for m in _ROOT_RE.finditer(code.blank):
        found.append(code.src[m.start(2):m.end(2)])
    if not found:
        return None, ["no literal record selector found"]
    notes = []
    if len(set(found)) > 1:
        notes.append(f"multiple record selectors present ({', '.join(sorted(set(found)))}); using the first")
    return found[0], notes


def _index_assignments(code: _Blanked) -> dict[str, list[_Blanked]]:
    """identifier -> every right-hand side assigned to it, in source order.

    Several entries for one name is not an error: it is how branching shows up. P1's correct heal
    assigns `priceValue` twice, once per arm of an if/else, and both arms are genuinely possible
    sources for the field. Collapsing them to the last one would hide half the truth.
    """
    out: dict[str, list[_Blanked]] = {}
    for m in _ASSIGN_RE.finditer(code.blank):
        name = m.group(1)
        if name in _RESERVED:
            continue
        rhs_start = m.end()
        rhs_end = _end_of_statement(code.blank, rhs_start)
        if rhs_end is None:
            continue                      # no clean terminator - skip rather than guess its extent
        out.setdefault(name, []).append(code.sub(rhs_start, rhs_end))
    return out


def _end_of_statement(blank: str, start: int) -> Optional[int]:
    """Index of the ';' or ',' that closes an assignment's right-hand side, at nesting depth zero."""
    depth = 0
    for i in range(start, len(blank)):
        c = blank[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0 and c in ";,":
            return i
    return None


def _record_return(code: _Blanked) -> tuple[Optional[dict[str, _Blanked]], list[str]]:
    """The object literal that defines the OUTPUT RECORD, as key -> value expression.

    These collectors contain at least two `return {...}` statements: the per-item record inside the
    `.map()` callback, and an outer `return { products }` wrapping the array. We want the first.

    The rule is "the return object with the most keys, and it must have at least two". That is a
    heuristic and it is worth being explicit about its failure mode: a collector whose record has a
    single field is indistinguishable from the container wrapper, so we decline rather than risk
    reporting the container's `products` key as if it were a data field. A tie for the maximum is
    likewise declined - two equally plausible candidates means we do not know which is the record.
    """
    candidates: list[dict[str, _Blanked]] = []
    for m in _RETURN_OBJ_RE.finditer(code.blank):
        open_idx = code.blank.index("{", m.start())
        close_idx = _match_brace(code.blank, open_idx)
        if close_idx is None:
            continue
        body = code.sub(open_idx + 1, close_idx)
        parsed = _parse_object_keys(body)
        if parsed:
            candidates.append(parsed)
    if not candidates:
        return None, ["no return object literal found"]
    best = max(len(c) for c in candidates)
    if best < 2:
        return None, ["record return object has fewer than two fields; cannot tell it from the container"]
    tied = [c for c in candidates if len(c) == best]
    if len(tied) > 1:
        return None, [f"{len(tied)} return objects with {best} fields each; record object is ambiguous"]
    return tied[0], []


def _parse_object_keys(body: _Blanked) -> dict[str, _Blanked]:
    """Split an object literal body into key -> value expression. Supports ES6 shorthand."""
    out: dict[str, _Blanked] = {}
    for start, end in _split_top_level(body, ","):
        segment_blank = body.blank[start:end]
        if not segment_blank.strip():
            continue
        colon = _top_level_colon(segment_blank)
        if colon is None:
            name = segment_blank.strip()
            if not re.fullmatch(r"[A-Za-z_$][\w$]*", name) or name in _RESERVED:
                return {}                     # spread, computed key, method - not a shape we read
            out[name] = body.sub(start, end)  # shorthand: the key IS the expression
            continue
        key_raw = segment_blank[:colon].strip()
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", key_raw):
            return {}
        out[key_raw] = body.sub(start + colon + 1, end)
    return out


def _top_level_colon(blank: str) -> Optional[int]:
    depth = 0
    for i, c in enumerate(blank):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ":" and depth == 0:
            # not part of '?:' - a ternary's colon is only reachable if a '?' preceded it at depth 0
            if "?" in blank[:i].replace("?.", "").replace("??", ""):
                return None
            return i
    return None


# --------------------------------------------------------------------------------------
# Expression resolution
# --------------------------------------------------------------------------------------

@dataclass
class _Resolution:
    selectors: list[SelectorRef]
    dynamic: bool = False
    constant: bool = False
    branches: int = 0
    exhausted: bool = False          # hit the depth cap - treat as unresolved


def _resolve_expression(expr: _Blanked, assigns: dict[str, list[_Blanked]],
                        seen: frozenset[str], depth: int) -> _Resolution:
    """Trace an expression back to the element(s) it reads, or give up loudly.

    The recognised shapes, in the order they are tried, and why each is safe:

      1. A literal `.find('sel')` or `$('sel')` anywhere in the expression IS the answer for that
         branch; we stop descending. Anything wrapped around it (`.text_sane()`, `parseFloat(...)`)
         only transforms the text, it does not change which element was read.

      2. `new Ctor(a, b, ...)` descends into `a` ONLY. This is specifically about Bright Data's
         `new Money(value, currency)`: the currency argument is very often derived from a second
         `.find()`, and unioning it into the field's sources would attribute every field that
         formats money to the element the currency symbol was scraped from. Following only the first
         argument keeps the answer to "where did the VALUE come from", which is the question.

      3. A top-level ternary descends into both arms and DROPS the condition. `x ? f(x) : null` -
         the condition tests the value, it does not produce it, and the value is reachable through
         the arm anyway.

      4. Otherwise, descend into every identifier in value position that has an assignment we
         indexed. Property names and callee names are excluded by the identifier pattern.

    Anything not covered lands in (4) and simply resolves to nothing, which is reported as
    unresolved rather than as "reads no element".
    """
    if depth > _MAX_DEPTH:
        return _Resolution([], exhausted=True)

    refs, dynamic = _find_selectors(expr)
    if dynamic:
        return _Resolution([], dynamic=True)
    if refs:
        return _Resolution(refs)

    if _CONSTANT_RE.match(expr.blank):
        return _Resolution([], constant=True)

    # (2) constructor call - value is the first argument
    m = _NEW_CALL_RE.search(expr.blank)
    if m and _is_top_level(expr.blank, m.start()):
        open_paren = expr.blank.index("(", m.end() - 1)
        close_paren = _match_brace(expr.blank, open_paren)
        if close_paren is not None:
            args = expr.sub(open_paren + 1, close_paren)
            first = _split_top_level(args, ",")[0]
            return _resolve_expression(args.sub(*first), assigns, seen, depth + 1)

    # (3) ternary - both arms, no condition
    arms = _ternary_arms(expr)
    if arms is not None:
        merged = _Resolution([])
        for arm in arms:
            sub = _resolve_expression(arm, assigns, seen, depth + 1)
            merged = _merge(merged, sub)
        merged.branches = max(merged.branches, len(arms))
        return merged

    # (4) follow locals
    merged = _Resolution([])
    followed = 0
    for name in _value_identifiers(expr.blank):
        if name in seen or name not in assigns:
            continue
        followed += 1
        for rhs in assigns[name]:
            sub = _resolve_expression(rhs, assigns, seen | {name}, depth + 1)
            merged = _merge(merged, sub)
            merged.branches = max(merged.branches, len(assigns[name]))
    if followed == 0 and not merged.selectors:
        return _Resolution([], constant=_CONSTANT_RE.match(expr.blank) is not None)
    return merged


def _merge(a: _Resolution, b: _Resolution) -> _Resolution:
    seen = {s.render() for s in a.selectors}
    merged = list(a.selectors)
    for s in b.selectors:
        if s.render() not in seen:
            seen.add(s.render())
            merged.append(s)
    return _Resolution(
        merged,
        dynamic=a.dynamic or b.dynamic,
        constant=a.constant or b.constant,
        branches=max(a.branches, b.branches),
        exhausted=a.exhausted or b.exhausted,
    )


def _is_top_level(blank: str, idx: int) -> bool:
    depth = 0
    for i in range(idx):
        c = blank[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
    return depth == 0


def _ternary_arms(expr: _Blanked) -> Optional[list[_Blanked]]:
    """Split `cond ? a : b` into [a, b], ignoring `?.` and `??`. None when it is not a ternary."""
    depth = 0
    q = None
    for i, c in enumerate(expr.blank):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "?" and depth == 0:
            nxt = expr.blank[i + 1:i + 2]
            if nxt in (".", "?"):
                continue
            if i and expr.blank[i - 1] == "?":
                continue
            q = i
            break
    if q is None:
        return None
    depth = 0
    nested = 0
    for i in range(q + 1, len(expr.blank)):
        c = expr.blank[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == "?" and expr.blank[i + 1:i + 2] not in (".", "?"):
            nested += 1
        elif depth == 0 and c == ":":
            if nested:
                nested -= 1
                continue
            return [expr.sub(q + 1, i), expr.sub(i + 1, len(expr.blank))]
    return None


def _value_identifiers(blank: str) -> list[str]:
    out: list[str] = []
    for m in _IDENT_RE.finditer(blank):
        name = m.group(1)
        if name in _RESERVED or name in out:
            continue
        out.append(name)
    return out


# --------------------------------------------------------------------------------------
# Whole-template extraction
# --------------------------------------------------------------------------------------

def parse_template(parse_code: Optional[str]) -> ParsedTemplate:
    """Build the field -> element map for one parser source.

    Public because it is useful on its own: pointed at a single template it answers "what does this
    collector read", which is the question an operator asks when a collector they did not write
    starts producing something odd.
    """
    if not isinstance(parse_code, str) or not parse_code.strip():
        return ParsedTemplate(ExtractionStatus.NO_PARSE_CODE, source=parse_code or "")

    blank = _blank_literals(parse_code)
    if blank is None:
        return ParsedTemplate(ExtractionStatus.UNREADABLE_SOURCE, source=parse_code,
                              notes=("source contains an unterminated string, comment or regex",))

    code = _Blanked(parse_code, blank)
    root, notes = _root_selector(code)
    record, record_notes = _record_return(code)
    notes = tuple(notes) + tuple(record_notes)
    if record is None:
        return ParsedTemplate(ExtractionStatus.UNRECOGNISED_SHAPE, root_selector=root,
                              notes=notes, source=parse_code)

    assigns = _index_assignments(code)
    fields: list[FieldSource] = []
    for name, expr in record.items():
        res = _resolve_expression(expr, assigns, frozenset(), 0)
        if res.dynamic:
            fields.append(FieldSource(name, resolved=False,
                                      reason="selector is computed at runtime, not a literal"))
        elif res.exhausted:
            fields.append(FieldSource(name, resolved=False,
                                      reason="resolution chain too deep to follow safely"))
        elif not res.selectors and not res.constant:
            fields.append(FieldSource(name, resolved=False,
                                      reason="value does not trace back to any element"))
        else:
            ordered = tuple(sorted(res.selectors, key=lambda s: s.render()))
            fields.append(FieldSource(
                name, ordered, resolved=True,
                conditional=len(ordered) > 1,
                has_constant_branch=res.constant and bool(ordered),
            ))
    return ParsedTemplate(ExtractionStatus.OK, root_selector=root, fields=tuple(fields),
                          notes=notes, source=parse_code)


# ======================================================================================
# Layer 3 - the diff
# ======================================================================================

def _extract_parse_code(template: Any) -> Optional[str]:
    """Pull `parse_code` out of a legacy-diff template, tolerating the shapes we have observed.

    Both `steps[0].parse_code` and `steps[0].parser.parser` carried byte-identical source in all six
    captured heals, so either is acceptable; we prefer `parse_code` because it is the documented one
    and fall back rather than fail if a future response only carries the other.
    """
    if isinstance(template, str):
        return template
    if not isinstance(template, dict):
        return None
    steps = template.get("steps")
    if not isinstance(steps, list) or not steps:
        return template.get("parse_code") if isinstance(template.get("parse_code"), str) else None
    step = steps[0]
    if not isinstance(step, dict):
        return None
    code = step.get("parse_code")
    if isinstance(code, str) and code.strip():
        return code
    parser = step.get("parser")
    if isinstance(parser, dict) and isinstance(parser.get("parser"), str):
        return parser["parser"]
    return None


def _line_change_counts(a: str, b: str, blank_a: Optional[str], blank_b: Optional[str]) -> tuple[int, int]:
    """How many changed lines were comment/blank, and how many carried code.

    This is what lets a brief say "3 comments rewritten, 4 lines of guard logic added, no field
    repointed" instead of "the parser changed". The healthy-page probe in the study is exactly that
    case, and describing it in scary terms is how you train an operator to stop reading.
    """
    a_lines, b_lines = a.splitlines(), b.splitlines()
    ba = (blank_a or a).splitlines()
    bb = (blank_b or b).splitlines()
    comment_lines = code_lines = 0
    sm = difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for idx, blanked in ((range(i1, i2), ba), (range(j1, j2), bb)):
            for k in idx:
                stripped = blanked[k].strip() if k < len(blanked) else ""
                if stripped:
                    code_lines += 1
                else:
                    comment_lines += 1
    return comment_lines, code_lines


def _normalised(blank: str) -> str:
    """Comment-free, whitespace-insensitive source. Equality here means 'cosmetic change only'."""
    lines = []
    for line in blank.splitlines():
        collapsed = " ".join(line.split())
        if collapsed:
            lines.append(collapsed)
    return "\n".join(lines)


def diff_templates(raw_diff: Any) -> TemplateDiff:
    """Compare the current and proposed parsers and report what the heal actually changed.

    Accepts `{"template_a": ..., "template_b": ...}` - the `diff` object from a
    `scraper heal --legacy-output` response - or the whole response, since callers holding one
    naturally hold the other.

    Never raises on malformed input. A heal decision must not fall over because an undocumented
    field changed shape upstream; it degrades to `ChangeClass.UNKNOWN`, which asserts nothing.
    """
    if isinstance(raw_diff, dict) and "template_a" not in raw_diff and isinstance(raw_diff.get("diff"), dict):
        raw_diff = raw_diff["diff"]
    if not isinstance(raw_diff, dict) or "template_a" not in raw_diff or "template_b" not in raw_diff:
        return TemplateDiff(ExtractionStatus.NO_DIFF, ChangeClass.UNKNOWN,
                            "No template diff was returned with this heal.")

    src_a = _extract_parse_code(raw_diff.get("template_a"))
    src_b = _extract_parse_code(raw_diff.get("template_b"))
    if not src_a or not src_b:
        return TemplateDiff(ExtractionStatus.NO_PARSE_CODE, ChangeClass.UNKNOWN,
                            "The heal diff carried no readable parser source.")

    if src_a == src_b:
        return TemplateDiff(ExtractionStatus.OK, ChangeClass.IDENTICAL,
                            "The proposed parser is byte-for-byte identical to the current one.")

    parsed_a = parse_template(src_a)
    parsed_b = parse_template(src_b)
    blank_a = _blank_literals(src_a)
    blank_b = _blank_literals(src_b)
    comment_lines, code_lines = _line_change_counts(src_a, src_b, blank_a, blank_b)

    cosmetic_only = (
        blank_a is not None and blank_b is not None
        and _normalised(blank_a) == _normalised(blank_b)
    )

    notes = tuple(parsed_a.notes) + tuple(parsed_b.notes)

    if not (parsed_a.ok and parsed_b.ok):
        # We could not build a field map. If the ONLY difference was comments we can still say that
        # much honestly, because it needs no field map - it is a property of the text.
        if cosmetic_only:
            return TemplateDiff(
                ExtractionStatus.OK, ChangeClass.COSMETIC,
                f"Comments and formatting only ({comment_lines} lines); no code changed.",
                comment_lines_changed=comment_lines, code_lines_changed=code_lines,
                notes=notes, template_a=parsed_a, template_b=parsed_b,
            )
        status = parsed_a.status if not parsed_a.ok else parsed_b.status
        return TemplateDiff(
            status, ChangeClass.UNKNOWN,
            "The proposed parser changed, but its source is not in a shape Vouch can read - "
            "judge this heal on its values alone.",
            comment_lines_changed=comment_lines, code_lines_changed=code_lines,
            notes=notes, template_a=parsed_a, template_b=parsed_b,
        )

    changes, unresolved, swaps, collisions, extra_notes = _compare(parsed_a, parsed_b)
    notes = notes + tuple(extra_notes)
    root_changed = parsed_a.root_selector != parsed_b.root_selector

    if cosmetic_only:
        classification = ChangeClass.COSMETIC
    elif changes or root_changed:
        classification = ChangeClass.REPOINTED
    else:
        classification = ChangeClass.LOGIC_ONLY

    return TemplateDiff(
        status=ExtractionStatus.OK,
        classification=classification,
        summary=_summarise(classification, changes, swaps, collisions, root_changed,
                           parsed_a, parsed_b, comment_lines, code_lines),
        field_changes=tuple(changes),
        swapped_pairs=tuple(swaps),
        collisions=tuple(collisions),
        root_before=parsed_a.root_selector,
        root_after=parsed_b.root_selector,
        unresolved_fields=tuple(unresolved),
        comment_lines_changed=comment_lines,
        code_lines_changed=code_lines,
        notes=notes,
        template_a=parsed_a,
        template_b=parsed_b,
    )


def _compare(a: ParsedTemplate, b: ParsedTemplate):
    """Field-by-field comparison of two resolved templates.

    The rule that does the most work: a field unresolved on EITHER side produces no change claim at
    all. Half a map is not evidence, and "we could not read this field" is a sentence an operator can
    do something with, whereas a change inferred from half a map is one they cannot check.
    """
    a_fields, b_fields = a.by_name(), b.by_name()
    a_vocab = a.vocabulary()
    b_vocab = b.vocabulary()

    changes: list[FieldChange] = []
    unresolved: list[tuple[str, str]] = []
    notes: list[str] = []

    for name in list(a_fields) + [n for n in b_fields if n not in a_fields]:
        fa, fb = a_fields.get(name), b_fields.get(name)
        if (fa and not fa.resolved) or (fb and not fb.resolved):
            reason = (fa.reason if fa and not fa.resolved else fb.reason) or "unknown"
            unresolved.append((name, reason))
            continue
        if fa is None:
            changes.append(FieldChange(name, "added", after=fb.keys,
                                       borrowed_from=tuple(sorted(_borrowers(fb.keys, a_vocab, name)))))
            continue
        if fb is None:
            changes.append(FieldChange(name, "removed", before=fa.keys))
            continue
        if fa.keys == fb.keys:
            continue
        gained = tuple(k for k in fb.keys if k not in fa.keys)
        changes.append(FieldChange(
            name, "repointed", before=fa.keys, after=fb.keys,
            borrowed_from=tuple(sorted(_borrowers(gained, a_vocab, name))),
            conditional_now=fb.conditional,
            retained=any(k in fb.keys for k in fa.keys),
        ))

    # A swap is mutual borrowing: each took the element the other had. Reported separately because
    # it is qualitatively stronger evidence than two independent repoints - a page rename can move
    # both fields, but it cannot make them cross.
    by_name = {c.field: c for c in changes}
    swaps: list[tuple[str, str]] = []
    for c in changes:
        for other in c.borrowed_from:
            oc = by_name.get(other)
            if oc and c.field in oc.borrowed_from:
                pair = tuple(sorted((c.field, other)))
                if pair not in swaps:
                    swaps.append(pair)  # type: ignore[arg-type]

    # Two fields reading one element means one of them is now a copy of the other. That is how the
    # 'price := shipping' heal ended up with price and shipping holding the same number.
    collisions: list[tuple[str, str]] = []
    for key, owners in b_vocab.items():
        if len(owners) < 2:
            continue
        if a_vocab.get(key, set()) >= owners:
            continue                       # they already shared this element before the heal
        for i, x in enumerate(sorted(owners)):
            for y in sorted(owners)[i + 1:]:
                if (x, y) not in collisions:
                    collisions.append((x, y))

    # The reassuring counterpart to cross-field borrowing, and worth saying out loud. P3 renamed
    # every class on the page and every field followed it; the heal was correct. What makes that
    # shape safe is provable from the source alone: no field took over an element another field
    # already had, so no value can have moved between fields.
    if changes and not any(c.borrowed_from for c in changes):
        if all(k not in a_vocab for c in changes for k in c.after):
            notes.append("no new selector was previously read by another field - whatever else this "
                         "heal did, it is not moving values between existing fields")

    # Position-only disambiguation is fragile in a way class-based selection is not: insert one more
    # `.money` span into the markup and every field shifts. P2's page gave the healer no labels to
    # work with, so this is sometimes the only answer available - but the operator should know the
    # heal is now relying on DOM order.
    positional_bases: dict[str, set[str]] = {}
    for f in b.fields:
        if not f.resolved:
            continue
        for s in f.selectors:
            if s.positional:
                positional_bases.setdefault(s.selector, set()).add(f.name)
    for base, owners in sorted(positional_bases.items()):
        if len(owners) >= 2:
            notes.append(f"{', '.join(sorted(repr(o) for o in owners))} are now told apart only by "
                         f"their position within '{base}', not by any class or label")

    return changes, unresolved, swaps, collisions, notes


def _borrowers(keys: Iterable[str], vocab: dict[str, set[str]], exclude: str) -> set[str]:
    out: set[str] = set()
    for k in keys:
        out |= {n for n in vocab.get(k, set()) if n != exclude}
    return out


def _summarise(classification: ChangeClass, changes, swaps, collisions, root_changed,
               a: ParsedTemplate, b: ParsedTemplate, comment_lines: int, code_lines: int) -> str:
    if classification is ChangeClass.COSMETIC:
        return f"Comments and formatting only ({comment_lines} lines); no code changed."
    if classification is ChangeClass.LOGIC_ONLY:
        return (f"Parser logic changed ({code_lines} lines) but every field still reads the same "
                f"element - no field was repointed.")
    # The lead sentence is ordered by how much a human should care, not by what is easiest to say.
    # Cross-field borrowing first, because that is the one shape the value-level battery goes blind
    # to at the 2-row gate; a wholesale rename last, because it is loud but usually benign.
    parts: list[str] = []
    if swaps:
        pairs = ", ".join(f"'{x}'/'{y}'" for x, y in swaps)
        parts.append(f"{pairs} now read each other's previous elements")
    borrowed = [c for c in changes if c.borrowed_from]
    if borrowed and not swaps:
        c = borrowed[0]
        parts.append(f"'{c.field}' now reads {_join(c.after)}, the element "
                     f"{', '.join(repr(n) for n in c.borrowed_from)} read before")
    if collisions:
        pairs = ", ".join(f"'{x}'/'{y}'" for x, y in collisions)
        parts.append(f"{pairs} read the same element")
    if root_changed:
        parts.append(f"the record selector moved from {_q(a.root_selector)} to {_q(b.root_selector)}")
    if not parts or (root_changed and len(changes) > 1):
        names = ", ".join(f"'{c.field}'" for c in changes)
        parts.append(f"{len(changes)} field(s) repointed ({names})")
    lead = "The heal repoints fields" if borrowed or swaps else "The heal changes what is read"
    return lead + ": " + "; ".join(parts) + "."
