"""Render the README sample table from metrics.jsonl (every variant the
pipeline ever produced is a row; the table wants honest numbers, not curated
ones). Old rows may carry retired extra keys — only the keys printed here are
read, so mixed-schema files stay parseable.

Run: python scripts/build-metrics-table.py [path/to/metrics.jsonl]
"""

from __future__ import annotations

import json
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "metrics/metrics.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in open(PATH)]
    if not rows:
        print("no metrics yet")
        return

    print("| # | prompt | model | latency (ms) | cost (USD) |")
    print("|---|--------|-------|--------------|------------|")
    for i, r in enumerate(rows[-30:], start=1):
        print(f"| {i} | {r['prompt'][:30]} | {r['model']} "
              f"| {r['latency_ms']} | {r['cost_usd']:.3f} |")

    cost = sum(r["cost_usd"] for r in rows)
    print(f"\n**{len(rows)} variants** · total cost ${cost:.2f}")


if __name__ == "__main__":
    main()
