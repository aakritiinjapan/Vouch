"""
Pin the whole suite to the hand-written fixture, whatever the app's demo default is.

The app defaults to `newegg_live` - the dataset derived from the real collector run - because the
demo has to show real products rather than invented ones. The tests deliberately do NOT follow that
default, for two reasons:

  1. `sample_runs.json` carries `original_price`, which the live collector never captured. Without
     it, test_value_ordering.py cannot exercise Tier 2c at all, and that tier covers the one failure
     mode the distributional checks are structurally blind to.
  2. Tests assert on specific values. Regenerating the demo dataset from a fresh collector run would
     otherwise rewrite the suite's expectations underneath it, which is exactly the kind of coupling
     that makes a test suite stop meaning anything.

Autouse and session-scoped, so no individual test has to remember.
"""

from __future__ import annotations

import pytest

from app.config import settings

TEST_DATASET = "sample_runs"


@pytest.fixture(autouse=True, scope="session")
def _pin_fixture_dataset():
    previous = settings.demo_dataset
    settings.demo_dataset = TEST_DATASET
    yield
    settings.demo_dataset = previous
