"""Adapter: build a guardian LLMConfig from the server's own settings.

Kept OUT of app.guardian on purpose. The guardian core is provider-agnostic and reads no global
state - it takes an LLMConfig. This is the one place that translates the server's settings into one,
for the INTERNAL repricer cycle. The public /verify endpoint does not use this: it builds an
LLMConfig from the caller's bring-your-own-key request instead, so Vouch never spends its own tokens
on a stranger's call.
"""

from __future__ import annotations

from app.config import settings
from app.guardian.judge import LLMConfig


def judge_config_from_settings() -> LLMConfig:
    return LLMConfig(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key or settings.anthropic_api_key,
        model=settings.llm_judge_model,
        base_url=settings.llm_base_url or None,
        enabled=not settings.mock_mode,
    )
