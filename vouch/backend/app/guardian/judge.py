"""
Tier 3 — LLM-as-judge (the semantic backstop).

Runs ONLY on a small sample (10–20 rows) and ONLY when the cheap deterministic checks are
ambiguous — so it's a scalpel, not a sledgehammer. For each field it asks: does this value still
represent what the field is supposed to mean? Returns a per-field pass rate that verdict.py folds
into the confidence score.

Phase 3: wire the Anthropic SDK. Prompt shape below. Keep output strict JSON and parse defensively.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.config import settings


@dataclass
class JudgeResult:
    field_scores: dict[str, float]        # field -> fraction of sampled rows judged correct (0..1)
    notes: str = ""


_PROMPT_TEMPLATE = """You are validating scraped data after an automatic extraction fix.
Field: "{field}"
This field should represent: {description}
Here are sampled values that were just extracted:
{values}

For each value, answer whether it plausibly represents the field's meaning.
Return ONLY JSON: {{"correct": <int>, "total": <int>, "reason": "<one line>"}}"""


def judge_fields(records: list[dict], field_descriptions: dict[str, str],
                 sample_size: int = 15) -> JudgeResult:
    if settings.mock_mode or not settings.anthropic_api_key:
        # deterministic stand-in so the pipeline runs offline
        return JudgeResult(field_scores={k: 1.0 for k in field_descriptions},
                           notes="mock judge: all fields assumed valid")

    sample = random.sample(records, min(sample_size, len(records)))
    scores: dict[str, float] = {}

    # from anthropic import Anthropic
    # client = Anthropic(api_key=settings.anthropic_api_key)
    for field_name, description in field_descriptions.items():
        values = [r.get(field_name) for r in sample]
        _prompt = _PROMPT_TEMPLATE.format(field=field_name, description=description, values=values)
        # msg = client.messages.create(model=settings.llm_judge_model, max_tokens=200,
        #                               messages=[{"role": "user", "content": _prompt}])
        # parsed = json.loads(msg.content[0].text)
        # scores[field_name] = parsed["correct"] / max(parsed["total"], 1)
        scores[field_name] = 1.0  # placeholder until wired
    return JudgeResult(field_scores=scores)
