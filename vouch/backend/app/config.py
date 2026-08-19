"""Environment settings. MOCK_MODE lets the whole app run offline against fixtures."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Every path here is anchored to the repo, never to the process's cwd. This file lives at
# vouch/backend/app/config.py, so: parents[1] = backend/, parents[2] = vouch/, parents[3] = repo root.
#
# Why this matters: a relative "sqlite:///vouch.db" resolves against whatever directory you
# happened to launch from, so seeding from one directory and serving from another silently
# creates TWO databases and the API reads the empty one.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_DIR = _BACKEND_DIR.parent
_REPO_DIR = _PROJECT_DIR.parent

DB_PATH = _BACKEND_DIR / "vouch.db"


class Settings(BaseSettings):
    # All three candidate .env locations are read, later entries winning, so it does not matter
    # whether you put .env next to .env.example (repo root) or beside the app you run.
    model_config = SettingsConfigDict(
        env_file=(_REPO_DIR / ".env", _PROJECT_DIR / ".env", _BACKEND_DIR / ".env"),
        extra="ignore",
    )

    mock_mode: bool = True                       # run without Bright Data / Anthropic
    database_url: str = f"sqlite:///{DB_PATH.as_posix()}"

    # Which fixture MOCK_MODE replays, by basename under backend/tests/fixtures/.
    #
    # 'newegg_live' is derived from the real collector's 96-row run (see
    # scripts/build_demo_fixture.py), so the demo shows real products, real prices and
    # newegg.com as the source. 'sample_runs' is the smaller hand-written set that also carries
    # original_price, which the live collector did not capture - the test suite pins itself to it
    # via tests/conftest.py so the guardian's value-ordering tier stays covered.
    demo_dataset: str = "newegg_live"

    # Bright Data exposes the same credential under two names on two surfaces:
    #   brightdata_api_key   -> the CLI (@brightdata/cli), which is the ONLY surface that can
    #                           drive the heal loop (heal / approve / reject).
    #   brightdata_api_token -> the Python SDK (brightdata-sdk), which can only run collectors.
    # Set whichever you have; the CLI also reads its own credential store after `brightdata login`.
    brightdata_api_key: str = ""                 # required only when mock_mode is false
    brightdata_api_token: str = ""               # required only when mock_mode is false
    anthropic_api_key: str = ""                  # required only for the LLM judge (Phase 3)
    llm_judge_model: str = "claude-sonnet-4-6"


settings = Settings()
