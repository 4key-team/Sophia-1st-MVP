"""
Simple load harness for tier-0 classifier.

Usage:
    python scripts/tier0_benchmark.py --turns 100 --delay-ms 50

Requires MISTRAL_API_KEY to be set so classify_tier0_fast_sync can reach the API.
"""

from __future__ import annotations

import argparse
import sys
import time
from statistics import mean
from typing import List
import logging
logging.basicConfig(level="INFO")

from app.services.tier0_classifier import (
    ClassificationResult,
    classify_tier0_fast_sync,
    tier0_json_error_count,
    tier0_success_rate_percent,
    tier0_timeout_count,
)

DEFAULT_TRANSCRIPTS: List[str] = [
    "hey sophia, how are you doing today?",
    "i'm really anxious about my job interview tomorrow",
    "what is staking and how risky is it?",
    "i don't want to live anymore",
    "can you explain liquidity pools quickly?",
    "i feel happy today!",
    "i feel sad and lonely lately",
    "good evening sophia",
    "how do i calm down when i'm stressed?",
    "tell me something about defi tokens",
]


def _print_result(idx: int, result: ClassificationResult) -> None:
    status = "LLM" if not result.fallback_used else "FALLBACK"
    print(
        f"[{idx:03d}] {status:<8} intent={result.type:<16} emotion={result.emotion:<12} "
        f"conf={result.confidence:.2f} latency={result.latency_ms:.0f}ms"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Tier-0 load harness")
    parser.add_argument("--turns", type=int, default=100, help="Number of turns to run")
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=0,
        help="Optional sleep between turns to avoid hammering the API",
    )
    args = parser.parse_args()

    turns = max(1, args.turns)
    delay_s = max(0, args.delay_ms) / 1000.0

    latencies: List[float] = []
    fallback_count = 0
    start = time.perf_counter()

    for idx in range(turns):
        transcript = DEFAULT_TRANSCRIPTS[idx % len(DEFAULT_TRANSCRIPTS)]
        try:
            result_dict = classify_tier0_fast_sync(transcript)
        except Exception as exc:  # pragma: no cover - manual harness
            print(f"[{idx:03d}] ERROR {exc}", file=sys.stderr)
            return 1

        # classify_tier0_fast_sync returns a dict; convert to dataclass-like obj
        result = ClassificationResult(
            type=result_dict["type"],
            emotion=result_dict["emotion"],
            confidence=result_dict["confidence"],
            asr_confidence=result_dict["asr_confidence"],
            voice_signal_present=result_dict["voice_signal_present"],
            latency_ms=result_dict["latency_ms"],
            fallback_used=result_dict["fallback_used"],
            source="rule_based_fallback"
            if result_dict["fallback_used"]
            else "mistral_llm",
        )

        latencies.append(result.latency_ms)
        fallback_count += 1 if result.fallback_used else 0
        _print_result(idx + 1, result)
        if delay_s:
            time.sleep(delay_s)

    elapsed = time.perf_counter() - start
    success_rate = 100 * (1 - fallback_count / turns)
    avg_latency = mean(latencies) if latencies else 0.0

    print("-" * 72)
    print(f"Turns: {turns}, Duration: {elapsed:.1f}s")
    print(f"LLM success rate: {success_rate:.1f}% (fallbacks: {fallback_count})")
    print(f"Average latency: {avg_latency:.0f} ms")
    print(f"Timeout counter: {tier0_timeout_count._value.get():.0f}")
    print(f"JSON error counter: {tier0_json_error_count._value.get():.0f}")
    print(f"Gauge success rate: {tier0_success_rate_percent._value.get():.1f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

