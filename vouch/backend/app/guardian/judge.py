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
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.config import settings

log = logging.getLogger(__name__)

# What each field is supposed to MEAN. This is the ground truth the judge measures against, so it is
# worth writing carefully - it is the only place the semantic intent of the schema is written down.
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
    "You validate scraped e-commerce data after an automatic extraction fix. A fix can return "
    "correctly-shaped values that mean the wrong thing - the shipping cost in the price column, a "
    "crossed-out list price instead of the sale price, a financing instalment instead of a total. "
    "Judge only whether each value plausibly represents its field's stated meaning. Do not judge "
    "whether a price is high or low."
)

_PROMPT = """Here are {n} sampled rows that an automatic fix just extracted:

{rows}

Assess each of these fields:
{fields}

For each field, report how many of the {n} shown values plausibly represent that field's meaning."""


def judge_fields(records: list[dict],
                 field_descriptions: dict[str, str] | None = None,
                 sample_size: int = 15) -> JudgeResult:
    """Ask the model whether each field's values still mean what the field says.

    Returns all-1.0 scores without calling out when running mocked or unconfigured, so the pipeline
    stays offline and deterministic. `consulted` distinguishes "the judge approved" from "the judge
    was never asked", which matters because only the former should move a verdict.
    """
    descriptions = field_descriptions or FIELD_DESCRIPTIONS
    # Only judge fields we actually have a stated meaning for and that are present in the data.
    present = {k for row in records for k in row}
    descriptions = {k: v for k, v in descriptions.items() if k in present}

    if settings.mock_mode or not settings.anthropic_api_key or not records or not descriptions:
        return JudgeResult(field_scores={k: 1.0 for k in descriptions},
                           notes="judge not consulted (mock mode, no API key, or nothing to judge)",
                           consulted=False)

    sample = random.sample(records, min(sample_size, len(records)))
    rows = "\n".join(f"  {i + 1}. {json.dumps(row, default=str)}" for i, row in enumerate(sample))
    fields = "\n".join(f'  - "{name}": {desc}' for name, desc in descriptions.items())

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.parse(
            model=settings.llm_judge_model,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": _PROMPT.format(n=len(sample), rows=rows, fields=fields),
            }],
            output_format=_Assessment,
        )
        assessment = response.parsed_output
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
                       notes=f"judged {len(sample)} sampled rows across {len(scores)} field(s)")
