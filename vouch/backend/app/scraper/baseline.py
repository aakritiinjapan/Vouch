"""
Capture the last-known-good profile of a collector's output.

Call this after any run/heal the guardian PASSED — it becomes the reference the next heal is judged
against. Store the returned dict on a Baseline row (models.Baseline.field_profiles).
"""

from __future__ import annotations

from app.guardian.checks import profile_run


def capture(records: list[dict]) -> tuple[dict, int]:
    """Return (field_profiles_as_json_dict, record_count) ready to persist on a Baseline row."""
    profiles = profile_run(records)
    as_json = {name: prof.to_dict() for name, prof in profiles.items()}
    return as_json, len(records)
