"""
The verification service - the Trust API's single core operation.

Given candidate rows and a baseline reference, run the guardian's pure pipeline
(run_all_checks -> decide -> optional Tier 3 judge) and return the verdict. This is the ONE place
that touches app/guardian; both the public POST /verify endpoint and the internal repricer cycle
call it, so there is exactly one verification code path in the system.

It is stateless and DB-free. Input shaping and HTTP concerns (status codes, the row cap, the caller's
X-LLM-Key) stay in the route; the repricer supplies its own already-stored profiles and its own
LLMConfig. Neither caller reaches past this boundary into the guardian.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.guardian.checks import FieldProfile, run_all_checks
from app.guardian.judge import LLMConfig, judge_fields
from app.guardian.verdict import REVIEW, Verdict, apply_judge, decide
from app.scraper import baseline as baseline_capture


@dataclass
class VerifyOutcome:
    """The verdict plus whether the paid Tier 3 judge was actually consulted (the endpoint reports
    the latter; the repricer ignores it)."""
    verdict: Verdict
    judge_consulted: bool = False


def verify_rows(*,
                candidate_records: list[dict],
                baseline_profiles: Optional[dict[str, dict]] = None,
                baseline_records: Optional[list[dict]] = None,
                baseline_count: Optional[int] = None,
                is_sample: bool = False,
                orderings: Optional[list[tuple[str, str]]] = None,
                field_descriptions: Optional[dict[str, str]] = None,
                use_judge: bool = False,
                llm_config: Optional[LLMConfig] = None) -> VerifyOutcome:
    """Verify candidate rows against a baseline. Exactly one of baseline_profiles (serialized
    FieldProfiles, e.g. a stored Baseline) or baseline_records (raw rows, profiled here) is required.

    Malformed serialized profiles raise TypeError/ValueError - the HTTP adapter turns those into 422;
    the repricer passes profiles it stored itself, so it never trips them.
    """
    if (baseline_profiles is None) == (baseline_records is None):
        raise ValueError("provide exactly one of baseline_profiles or baseline_records")

    if baseline_records is not None:
        serialized, inferred_count = baseline_capture.capture(baseline_records)
    else:
        serialized, inferred_count = baseline_profiles, None

    profiles = {name: FieldProfile.from_dict(prof) for name, prof in serialized.items()}

    if baseline_count is not None:
        count = baseline_count
    elif inferred_count is not None:
        count = inferred_count
    else:
        count = max((p.count for p in profiles.values()), default=0)

    results = run_all_checks(profiles, candidate_records, count,
                             is_sample=is_sample, orderings=orderings)
    verdict = decide(results)

    judge_consulted = False
    if use_judge and verdict.decision == REVIEW and llm_config is not None:
        judge_result = judge_fields(candidate_records, field_descriptions=field_descriptions,
                                    config=llm_config)
        verdict = apply_judge(verdict, judge_result)
        judge_consulted = judge_result.consulted

    return VerifyOutcome(verdict=verdict, judge_consulted=judge_consulted)
