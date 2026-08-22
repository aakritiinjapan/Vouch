"""
The Trust API's HTTP surface: POST /verify, and nothing else.

Kept in its own router so it can be mounted as a standalone sub-application with its OWN OpenAPI docs
(/trust/docs) - a developer integrating the Trust API sees only the one endpoint they need, not the
repricer's REST surface. The same router is also included on the main app so the dashboard proxy and
the existing tests keep hitting /verify.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException

from app.api import schemas
from app.trust import LLMConfig, verify_rows

trust_router = APIRouter(tags=["Trust API"])

# Profiling is O(rows x fields); /verify is a public, unauthenticated surface, so both caller-supplied
# lists are capped rather than left to consume unbounded CPU. Well above any real preview or baseline.
MAX_VERIFY_ROWS = 5000


@trust_router.post("/verify", response_model=schemas.VerifyResponse)
def verify(body: schemas.VerifyRequest = Body(...),
           x_llm_key: Optional[str] = Header(default=None, alias="X-LLM-Key")):
    """Thin HTTP adapter over the trust layer's verify_rows - no product, no baseline row, no
    pricing, no writes. It runs the exact same verification the repricer's orchestrator runs (both
    call verify_rows), exposed so any pipeline can gate on Vouch's confidence score and risk brief
    without adopting the repricer. Because it touches no database it takes no session dependency.

    Tier 3 is bring-your-own-key: the paid semantic judge only runs when the caller sets `use_judge`
    AND supplies their own model key in the `X-LLM-Key` header. Vouch never spends its own tokens on
    a public call, which is what makes this endpoint safe to expose without metering the LLM.
    """
    if not body.candidate_records:
        raise HTTPException(422, detail={"detail": "candidate_records must be non-empty"})
    if len(body.candidate_records) > MAX_VERIFY_ROWS:
        raise HTTPException(422, detail={
            "detail": f"candidate_records exceeds the {MAX_VERIFY_ROWS}-row limit"})
    if body.baseline_records is not None and len(body.baseline_records) > MAX_VERIFY_ROWS:
        raise HTTPException(422, detail={
            "detail": f"baseline_records exceeds the {MAX_VERIFY_ROWS}-row limit"})
    if (body.baseline_records is not None) == (body.baseline_profiles is not None):
        raise HTTPException(422, detail={
            "detail": "provide exactly one of baseline_records or baseline_profiles"})

    # Tier 3 config is built ONLY from the caller's own X-LLM-Key (never a server key), so the public
    # endpoint never spends Vouch's tokens. Without the header the judge stays a no-op.
    llm_config = None
    if body.use_judge and x_llm_key:
        llm = body.llm or schemas.VerifyLLMConfig()
        llm_config = LLMConfig(provider=llm.provider, api_key=x_llm_key,
                               model=llm.model or "", base_url=llm.base_url, enabled=True)

    # verify_rows rehydrates caller-supplied profiles via FieldProfile.from_dict, which raises on
    # wrong/missing keys. This endpoint ingests arbitrary caller data, so surface that as a 422.
    try:
        outcome = verify_rows(
            candidate_records=body.candidate_records,
            baseline_profiles=body.baseline_profiles,
            baseline_records=body.baseline_records,
            baseline_count=body.baseline_count,
            is_sample=body.is_sample,
            orderings=body.orderings,
            field_descriptions=body.field_descriptions,
            use_judge=body.use_judge,
            llm_config=llm_config,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, detail={"detail": f"malformed baseline_profiles: {exc}"})

    verdict = outcome.verdict
    return schemas.VerifyResponse(
        decision=verdict.decision,
        confirmed=verdict.confirmed,
        confidence=verdict.confidence,
        brief=verdict.brief,
        failures=[
            schemas.VerifyFailure(
                code=f.code,
                severity=f.severity.value,
                field=f.field_name,
                message=f.message,
                evidence=f.evidence,
            )
            for f in verdict.failures
        ],
        judge_consulted=outcome.judge_consulted,
    )
