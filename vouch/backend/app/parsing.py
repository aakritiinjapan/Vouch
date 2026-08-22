"""Small shared parsing helpers, dependency-free. A leaf module both the guardian's profiling and the
repricer's competitor-price matching use, so the repricer never has to import guardian internals."""

from __future__ import annotations

from typing import Any, Optional


def coerce_number(v: Any) -> Optional[float]:
    """Best-effort numeric parse: strips currency symbols, commas, whitespace."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    try:
        return float(s)
    except ValueError:
        return None
