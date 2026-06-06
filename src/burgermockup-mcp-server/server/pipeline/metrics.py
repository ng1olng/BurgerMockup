"""Per-variant metrics log. EVERY variant — pass and fail — appends a row;
the README sample table is generated from this file."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from server.contracts import MetricsRow

METRICS_PATH = os.environ.get("METRICS_PATH", "metrics/metrics.jsonl")


def log_variant(mockup_id: str, prompt: str, model: str, ssim: float,
                latency_ms: int, cost_usd: float) -> None:
    row = MetricsRow(
        mockup_id=mockup_id, prompt=prompt, model=model, ssim=round(ssim, 4),
        latency_ms=latency_ms, cost_usd=cost_usd,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    with open(METRICS_PATH, "a") as f:
        f.write(row.model_dump_json() + "\n")
