"""Host-controlled job abort. The host mints a high-entropy job_id per
generate/refine call and POSTs /jobs/{job_id}/abort to stop it; the variant
loop polls between variants. This replaces MCP-level cancellation, which is
not reliably supported over streamable HTTP.

Granularity is PER-VARIANT by design: an abort lets the one in-flight
generation finish (bounded cost: at most one paid image) and prevents every
subsequent variant. Cancelling mid-request buys little and risks leaving the
provider call in an undefined state.
"""

from __future__ import annotations

# Insertion-ordered so eviction drops the OLDEST abort flag, never a fresh one
# (set.pop() would evict arbitrarily and could un-abort a live job).
_aborted: dict[str, None] = {}

_MAX_TRACKED = 256


def abort(job_id: str) -> None:
    if len(_aborted) >= _MAX_TRACKED:
        _aborted.pop(next(iter(_aborted)))
    _aborted[job_id] = None


def is_aborted(job_id: str) -> bool:
    return job_id in _aborted


def clear(job_id: str) -> None:
    _aborted.pop(job_id, None)
