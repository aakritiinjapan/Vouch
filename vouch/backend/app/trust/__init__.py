"""
The Trust API layer - the one boundary the guardian is reached through.

`verify_rows` is the single verification entry point. `POST /verify` is a thin HTTP adapter over it,
and the repricer's orchestrator calls the exact same function - so the repricer is a genuine consumer
of the Trust API, not a second implementation, and `app/guardian` is imported ONLY from here.

`Verdict` is re-exported because it is the Trust API's output type; callers depend on the boundary,
never on `app.guardian` internals.
"""

from app.guardian.judge import LLMConfig
from app.guardian.verdict import Verdict
from app.trust.verify import VerifyOutcome, verify_rows

__all__ = ["verify_rows", "VerifyOutcome", "Verdict", "LLMConfig"]
