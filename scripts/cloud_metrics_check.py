"""
Utility script to validate tier-0 Prometheus metrics from a remote deployment.

Examples:
    python scripts/cloud_metrics_check.py \
        --metrics-url https://api.example.com/metrics \
        --min-success 80 \
        --max-latency 800 \
        --baseline-latency 1400 \
        --min-improvement 500
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Dict

import requests

METRIC_NAMES = {
    "success": "tier0_success_rate_percent",
    "timeout": "tier0_timeout_count",
    "json": "tier0_json_error_count",
    "latency_avg": "tier0_latency_avg_ms",
}


def parse_metrics(text: str) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        for key, metric in METRIC_NAMES.items():
            if line.startswith(metric):
                match = re.search(r"(-?\d+(?:\.\d+)?)$", line.strip())
                if match:
                    values[key] = float(match.group(1))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Check tier-0 Prometheus metrics")
    parser.add_argument("--metrics-url", required=True, help="Full URL to /metrics")
    parser.add_argument(
        "--min-success",
        type=float,
        default=80.0,
        help="Minimum acceptable success rate percent",
    )
    parser.add_argument(
        "--max-latency",
        type=float,
        default=800.0,
        help="Maximum acceptable average latency (ms)",
    )
    parser.add_argument(
        "--baseline-latency",
        type=float,
        default=None,
        help="Previous average latency in ms for improvement comparison",
    )
    parser.add_argument(
        "--min-improvement",
        type=float,
        default=500.0,
        help="Required improvement (baseline - current) in ms",
    )
    args = parser.parse_args()

    response = requests.get(args.metrics_url, timeout=10)
    response.raise_for_status()
    metrics = parse_metrics(response.text)

    missing = [metric for metric in METRIC_NAMES if metric not in metrics]
    if missing:
        print(f"Missing metrics in response: {missing}", file=sys.stderr)
        return 2

    success_rate = metrics["success"]
    avg_latency = metrics["latency_avg"]
    timeout_count = metrics["timeout"]
    json_errors = metrics["json"]

    print(
        f"tier0_success_rate_percent={success_rate:.1f}% "
        f"tier0_latency_avg_ms={avg_latency:.1f} "
        f"tier0_timeout_count={timeout_count:.0f} "
        f"tier0_json_error_count={json_errors:.0f}"
    )

    if success_rate < args.min_success:
        print(
            f"❌ Success rate {success_rate:.1f}% < required {args.min_success}%",
            file=sys.stderr,
        )
        return 3

    if avg_latency > args.max_latency:
        print(
            f"❌ Average latency {avg_latency:.1f}ms > allowed {args.max_latency}ms",
            file=sys.stderr,
        )
        return 4

    if args.baseline_latency is not None:
        improvement = args.baseline_latency - avg_latency
        if improvement < args.min_improvement:
            print(
                f"❌ Latency improvement {improvement:.1f}ms < required {args.min_improvement}ms",
                file=sys.stderr,
            )
            return 5
        print(f"✅ Latency improved by {improvement:.1f}ms from baseline")

    if json_errors > 0:
        print(
            f"⚠️ JSON parsing errors observed ({json_errors:.0f}); investigate responses",
            file=sys.stderr,
        )

    print("✅ Cloud metrics check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

