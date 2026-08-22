"""
Tier 3 - the semantic backstop, and the rules governing when it is allowed to move a verdict.

The judge never runs in the demo (MOCK_MODE short-circuits it), so these tests are the only thing
standing between it and a wrong verdict on live data. The rule worth protecting hardest: a model that
read the rows which ARE present may not vouch for rows that are missing.
"""

from __future__ import annotations

import pytest

from app.guardian import judge
from app.guardian.checks import CheckResult, Severity
from app.guardian.judge import JudgeResult, LLMConfig
from app.guardian.verdict import FAIL, PASS, REVIEW, apply_judge, decide

ROWS = [{"name": "MSI RTX 5080", "price": 1299.99, "shipping": 19.99}]


def _config(provider: str = "anthropic", key: str = "sk-test", enabled: bool = True) -> LLMConfig:
    return LLMConfig(provider=provider, api_key=key, model="test-model", enabled=enabled)


def _review_from(code: str, field_name: str = "price") -> object:
    """A REVIEW verdict caused by exactly one HIGH failure of the given code."""
    verdict = decide([CheckResult(False, Severity.HIGH, field_name, code,
                                  f"'{field_name}' looks suspicious.", {})])
    assert verdict.decision == REVIEW, "fixture must produce the ambiguous case"
    return verdict


def _judged(score: float, field_name: str = "price", reason: str = "") -> JudgeResult:
    return JudgeResult(field_scores={field_name: score}, reasons={field_name: reason},
                       consulted=True)


# --------------------------------------------------------------------------------------
# the gate: Tier 3 only runs on REVIEW
# --------------------------------------------------------------------------------------

def test_a_clean_pass_is_never_second_guessed():
    """Spending an API call to re-confirm a clean run is pure waste."""
    verdict = decide([])
    assert verdict.decision == PASS
    assert apply_judge(verdict, _judged(0.0)) is verdict, "returned untouched, not merely equal"


def test_a_critical_fail_is_never_revisited():
    """A column swap is already decided; a model cannot argue it back."""
    verdict = decide([CheckResult(False, Severity.CRITICAL, "price", "COLUMN_SWAP",
                                  "swapped", {"field": "price", "looks_like": "shipping"})])
    assert verdict.decision == FAIL
    assert apply_judge(verdict, _judged(1.0)) is verdict


def test_an_unconsulted_judge_changes_nothing():
    """The mock path returns all-1.0 scores. Those must NOT read as approval."""
    verdict = _review_from("NUMERIC_DRIFT")
    unconsulted = JudgeResult(field_scores={"price": 1.0}, consulted=False)
    assert apply_judge(verdict, unconsulted) is verdict


def test_an_unreachable_judge_leaves_the_deterministic_verdict_standing():
    verdict = _review_from("NUMERIC_DRIFT")
    assert apply_judge(verdict, JudgeResult(field_scores={}, consulted=False)) is verdict


# --------------------------------------------------------------------------------------
# escalation - the case Tier 3 exists for
# --------------------------------------------------------------------------------------

def test_the_judge_can_escalate_a_review_to_fail():
    """Values with an acceptable distribution but the wrong meaning: the statistics cannot see it."""
    verdict = _review_from("NUMERIC_DRIFT")
    result = apply_judge(verdict, _judged(0.2, reason="these look like monthly instalments"))

    assert result.decision == FAIL
    assert result.confidence == verdict.confidence - 30
    assert "monthly instalments" in result.brief
    assert result.failures == verdict.failures, "the deterministic findings are preserved"


def test_escalation_works_even_on_a_completeness_failure():
    """The judge may always confirm doubt - the asymmetry only restricts CLEARING it."""
    verdict = _review_from("NULL_SPIKE")
    assert apply_judge(verdict, _judged(0.1)).decision == FAIL


# --------------------------------------------------------------------------------------
# relaxation - and the asymmetry that constrains it
# --------------------------------------------------------------------------------------

def test_the_judge_can_clear_a_purely_distributional_doubt():
    verdict = _review_from("NUMERIC_DRIFT")
    result = apply_judge(verdict, _judged(1.0))

    assert result.decision == PASS
    assert result.confidence == min(100, verdict.confidence + 20)
    assert result.confirmed


@pytest.mark.parametrize("code", ["NULL_SPIKE", "FIELD_MISSING", "ROW_COUNT_SHIFT"])
def test_the_judge_may_not_clear_missing_data(code):
    """The rule worth protecting hardest.

    The judge read the values that ARE there. If the doubt is that data is ABSENT - a null spike, a
    dropped field, a collapsed row count - it has nothing to say, and letting it clear the hold would
    be the model vouching for rows it never saw.
    """
    verdict = _review_from(code)
    result = apply_judge(verdict, _judged(1.0))

    assert result.decision == REVIEW, f"{code} is about absence; a reader cannot clear it"
    assert not result.confirmed


def test_a_middling_score_leaves_the_verdict_alone():
    """Between the thresholds the judge has no opinion worth acting on."""
    verdict = _review_from("NUMERIC_DRIFT")
    assert apply_judge(verdict, _judged(0.75)) is verdict


def test_the_worst_field_drives_the_decision():
    """One bad field is enough; averaging would let a good field mask it."""
    verdict = _review_from("NUMERIC_DRIFT")
    mixed = JudgeResult(field_scores={"name": 1.0, "price": 0.1, "shipping": 1.0},
                        reasons={"price": "shipping costs, not prices"}, consulted=True)
    result = apply_judge(verdict, mixed)

    assert result.decision == FAIL
    assert "price" in result.brief


# --------------------------------------------------------------------------------------
# judge_fields short-circuits - bring-your-own-key: no usable config, no call
# --------------------------------------------------------------------------------------

def test_no_config_never_calls_out():
    """The demo path and any public caller who brought no key: deterministic-only, no call."""
    result = judge.judge_fields(ROWS)

    assert result.consulted is False
    assert set(result.field_scores) <= set(judge.FIELD_DESCRIPTIONS)
    assert "not consulted" in result.notes


def test_a_disabled_config_short_circuits():
    """A key can be present but the caller (e.g. the mocked demo) forces deterministic-only."""
    assert judge.judge_fields(ROWS, config=_config(enabled=False)).consulted is False


def test_a_missing_api_key_short_circuits():
    assert judge.judge_fields(ROWS, config=_config(key="")).consulted is False


def test_only_fields_present_in_the_data_are_judged():
    """No point asking about a field the collector does not return."""
    result = judge.judge_fields([{"price": 1.0}])
    assert set(result.field_scores) == {"price"}


def test_an_sdk_failure_is_swallowed_into_not_consulted(monkeypatch):
    """Tier 3 is a bonus. It must never be able to break a cycle."""
    import anthropic

    def explode(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(anthropic, "Anthropic", explode)
    result = judge.judge_fields(ROWS, config=_config())

    assert result.consulted is False
    assert "judge unavailable" in result.notes


def test_scores_are_derived_from_the_structured_response(monkeypatch):
    """Verifies the Anthropic parse path end to end without a network call."""
    import anthropic

    class FakeMessages:
        def parse(self, **_kwargs):
            class Response:
                parsed_output = judge._Assessment(fields=[
                    judge._FieldAssessment(field_name="price", correct=3, total=10,
                                           reason="these are shipping costs"),
                    judge._FieldAssessment(field_name="shipping", correct=10, total=10, reason="fine"),
                ])
            return Response()

    class FakeClient:
        def __init__(self, **_kwargs):
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    result = judge.judge_fields(ROWS, config=_config())

    assert result.consulted is True
    assert result.field_scores == {"price": 0.3, "shipping": 1.0}
    assert result.worst == ("price", 0.3)
    assert result.reasons["price"] == "these are shipping costs"


def test_the_openai_provider_path_is_used_when_selected(monkeypatch):
    """Provider-agnostic: an openai config routes through the OpenAI-compatible transport."""
    import openai

    class FakeCompletions:
        def parse(self, **_kwargs):
            class Msg:
                parsed = judge._Assessment(fields=[
                    judge._FieldAssessment(field_name="price", correct=2, total=10, reason="wrong")])

            class Choice:
                message = Msg()

            class Response:
                choices = [Choice()]
            return Response()

    class FakeClient:
        def __init__(self, **_kwargs):
            self.beta = type("B", (), {"chat": type("C", (), {"completions": FakeCompletions()})()})()

    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    result = judge.judge_fields(ROWS, config=_config(provider="openai"))

    assert result.consulted is True
    assert result.field_scores == {"price": 0.2}
    assert "openai" in result.notes


def test_a_zero_total_cannot_divide_by_zero(monkeypatch):
    import anthropic

    class FakeClient:
        def __init__(self, **_kwargs):

            class Messages:
                def parse(self, **_kwargs):
                    class Response:
                        parsed_output = judge._Assessment(fields=[
                            judge._FieldAssessment(field_name="price", correct=0, total=0, reason="")
                        ])
                    return Response()

            self.messages = Messages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    assert judge.judge_fields(ROWS, config=_config()).field_scores == {"price": 0.0}
