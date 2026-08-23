"""
Tier 3 - LLM-as-judge (the semantic backstop).

The deterministic tiers compare a heal against a statistical baseline. They are fast, free and
explainable, but they are blind to one case: a heal that returns values with a *plausible
distribution* which nonetheless mean the wrong thing. A per-month financing figure sitting where a
sale price belongs will not move a median far enough to trip NUMERIC_DRIFT.

So this runs ONLY when the cheap checks came back ambiguous (a REVIEW verdict) - never on a clean PASS
(waste) and never on a CRITICAL FAIL (already decided). That keeps it a scalpel: at most one API call
per held cycle, and none at all during the mocked demo.

One request judges every field at once. N requests for N fields would be N times the latency and cost
for strictly less context - the model can see, for instance, that `price` and `shipping` look swapped
only if it is shown both.

Bring-your-own-key, provider-agnostic. This module reads NO global config: the caller passes an
`LLMConfig` (which provider, which model, whose key). That is what lets the same guardian run inside
the repricer, a CI gate, or a stranger's pipeline on the public /verify surface without Vouch ever
holding anyone's credentials or paying for anyone's tokens. `app.llm` builds an LLMConfig from the
server's own settings for the internal repricer path; the public endpoint builds one from the
caller's request + `X-LLM-Key` header.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

log = logging.getLogger(__name__)

# What each field is supposed to MEAN. This is the ground truth the judge measures against, so it is
# worth writing carefully - it is the only place the semantic intent of the schema is written down.
# This is the repricer's DEFAULT; a caller with a different schema passes its own field_descriptions.
FIELD_DESCRIPTIONS: dict[str, str] = {
    "name": "the product's full retail name, including brand and model",
    "price": (
        "the product's own current selling price in USD - NOT the shipping or delivery cost, NOT a "
        "crossed-out original/list price, NOT a per-month financing figure, NOT a discount amount"
    ),
    "original_price": (
        "the crossed-out list or 'was' price the item is discounted FROM - always greater than or "
        "equal to the price actually charged today, never the price the customer pays"
    ),
    "shipping": (
        "the delivery cost for this one item in USD, frequently 0.00 for free shipping - never the "
        "item's own price"
    ),
    "rating": "the average customer review score, on a 0-5 scale",
    "in_stock": "whether this specific item is currently purchasable",
}

# How many sampled rows the judge must accept before its opinion counts either way.
CONFIRM_THRESHOLD = 0.9      # at or above: the judge corroborates that the meaning survived
REJECT_THRESHOLD = 0.6       # below: the judge confirms the doubt

# Default model per provider, used when an LLMConfig names a provider but no model.
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
}


@dataclass
class LLMConfig:
    """How to reach a judge model - supplied by the caller, never read from global state.

    `provider` is "anthropic" or "openai". "openai" also covers any OpenAI-compatible endpoint via
    `base_url` (most providers expose one), which is what makes this provider-agnostic without an
    adapter per vendor. `enabled` lets a caller force the deterministic-only path even with a key
    present (the mocked demo does this).
    """
    provider: str = "anthropic"
    api_key: str = ""
    model: str = ""
    base_url: Optional[str] = None
    enabled: bool = True

    @property
    def usable(self) -> bool:
        return self.enabled and bool(self.api_key)

    def resolved_model(self) -> str:
        return self.model or _DEFAULT_MODELS.get(self.provider, "")


@dataclass
class JudgeResult:
    field_scores: dict[str, float]        # field -> fraction of sampled rows judged correct (0..1)
    notes: str = ""
    reasons: dict[str, str] = field(default_factory=dict)
    consulted: bool = False               # False when we short-circuited instead of calling out

    @property
    def worst(self) -> tuple[str, float] | None:
        """The least convincing field - what a demotion should be attributed to."""
        if not self.field_scores:
            return None
        return min(self.field_scores.items(), key=lambda kv: kv[1])


# --------------------------------------------------------------------------------------
# structured output schema
# --------------------------------------------------------------------------------------

class _FieldAssessment(BaseModel):
    field_name: str
    correct: int          # how many of the shown values plausibly represent the field's meaning
    total: int
    reason: str           # one line, human-readable - this can end up in a risk brief


class _Assessment(BaseModel):
    fields: list[_FieldAssessment]


_SYSTEM = (
    "You validate scraped data after an automatic extraction fix. A fix can return "
    "correctly-shaped values that mean the wrong thing - the shipping cost in the price column, a "
    "crossed-out list price instead of the sale price, a financing instalment instead of a total. "
    "Judge only whether each value plausibly represents its field's stated meaning. Do not judge "
    "whether a value is high or low, only whether it is the RIGHT KIND of value for the field."
)

_PROMPT = """Here are {n} sampled rows that an automatic fix just extracted:

{rows}

Assess each of these fields:
{fields}

For each field, report how many of the {n} shown values plausibly represent that field's meaning."""


def judge_fields(records: list[dict],
                 field_descriptions: dict[str, str] | None = None,
                 config: LLMConfig | None = None,
                 sample_size: int = 15) -> JudgeResult:
    """Ask the model whether each field's values still mean what the field says.

    Returns all-1.0 scores without calling out when no usable `config` is given (the mocked demo,
    or a public caller who brought no key), so the pipeline stays offline and deterministic.
    `consulted` distinguishes "the judge approved" from "the judge was never asked", which matters
    because only the former should move a verdict.
    """
    descriptions = field_descriptions or FIELD_DESCRIPTIONS
    # Only judge fields we actually have a stated meaning for and that are present in the data.
    present = {k for row in records for k in row}
    descriptions = {k: v for k, v in descriptions.items() if k in present}

    if config is None or not config.usable or not records or not descriptions:
        return JudgeResult(field_scores={k: 1.0 for k in descriptions},
                           notes="judge not consulted (no usable LLM config, or nothing to judge)",
                           consulted=False)

    # Seed from a deterministic hash of the candidate records so the same proposal always
    # draws the same sample and produces a reproducible verdict, even when the judge is consulted
    # on multiple retries of the same heal attempt.
    seed = hash(tuple(sorted(str(r) for r in records)))
    rng = random.Random(seed)
    sample = rng.sample(records, min(sample_size, len(records)))
    rows = "\n".join(f"  {i + 1}. {json.dumps(row, default=str)}" for i, row in enumerate(sample))
    fields = "\n".join(f'  - "{name}": {desc}' for name, desc in descriptions.items())
    user_prompt = _PROMPT.format(n=len(sample), rows=rows, fields=fields)

    try:
        if config.provider == "openai":
            assessment = _call_openai(config, user_prompt)
        else:
            assessment = _call_anthropic(config, user_prompt)
    except Exception as exc:                      # noqa: BLE001 - never let Tier 3 break a cycle
        # A judge that cannot be reached must not change a verdict. Fall back to "not consulted" so
        # the deterministic tiers stand on their own, and say so out loud in the log.
        log.warning("Tier 3 judge unavailable, falling back to the deterministic verdict: %s", exc)
        return JudgeResult(field_scores={}, notes=f"judge unavailable: {exc}", consulted=False)

    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for item in assessment.fields:
        total = max(item.total, 1)
        scores[item.field_name] = max(0.0, min(1.0, item.correct / total))
        reasons[item.field_name] = item.reason

    return JudgeResult(field_scores=scores, reasons=reasons, consulted=True,
                       notes=f"judged {len(sample)} sampled rows across {len(scores)} field(s) "
                             f"via {config.provider}")


# --------------------------------------------------------------------------------------
# provider transports - each returns an _Assessment; only this layer is provider-specific
# --------------------------------------------------------------------------------------

def _call_anthropic(config: LLMConfig, user_prompt: str) -> _Assessment:
    from anthropic import Anthropic

    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = Anthropic(**kwargs)
    response = client.messages.parse(
        model=config.resolved_model(),
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=_Assessment,
    )
    return response.parsed_output


def _call_openai(config: LLMConfig, user_prompt: str) -> _Assessment:
    from openai import OpenAI

    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = OpenAI(**kwargs)
    response = client.beta.chat.completions.parse(
        model=config.resolved_model(),
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        response_format=_Assessment,
    )
    return response.choices[0].message.parsed
