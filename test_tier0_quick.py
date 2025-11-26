"""Quick test of tier-0 classifier rule-based functions (no LLM dependencies)"""

import re
import time

# Copy rule-based functions for testing
CRISIS_PATTERNS = [
    r"\b(kill|suicide|die|death|end.*life|hurt.*myself|harm.*myself)\b",
    r"\b(don'?t\s+want\s+to\s+live|want\s+to\s+die|life.*not.*worth)\b",
    r"\b(не.*хоч.*жить|суицид|убить.*себ|покончить|умер)",
    r"\b(cut.*myself|overdose|jump.*off|hang.*myself)\b",
    r"\b(better.*if.*died|end.*it.*all|take.*my.*life)\b",
]


def _detect_crisis(text: str) -> bool:
    text_lower = text.lower()
    for pattern in CRISIS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


# Test data
CRISIS_PHRASES = [
    "I want to kill myself",
    "I don't want to live anymore",
    "Thinking about suicide",
    "Я не хочу жить",
]

NON_CRISIS_PHRASES = [
    "Hello, how are you?",
    "I'm feeling happy",
    "What is DeFi?",
]


def test_crisis_detection():
    print("🧪 Testing crisis detection...")

    # Should detect crisis
    for phrase in CRISIS_PHRASES:
        result = _detect_crisis(phrase)
        status = "✅" if result else "❌"
        print(f"  {status} '{phrase[:40]}...' → Crisis: {result}")
        assert result, f"Failed to detect crisis: {phrase}"

    # Should not detect crisis
    for phrase in NON_CRISIS_PHRASES:
        result = _detect_crisis(phrase)
        status = "✅" if not result else "❌"
        print(f"  {status} '{phrase[:40]}...' → Crisis: {result}")
        assert not result, f"False positive: {phrase}"

    print("✅ Crisis detection tests passed!\n")


def test_performance():
    print("⚡ Testing performance...")

    phrase = "Hello, I'm worried about everything and want to know about DeFi"
    latencies = []

    for _ in range(100):
        start = time.perf_counter()
        _detect_crisis(phrase)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[94]
    print(f"  P95 latency: {p95:.3f}ms")
    print(f"  Min: {min(latencies):.3f}ms, Max: {max(latencies):.3f}ms")

    assert p95 < 1.0, f"P95 latency {p95:.3f}ms exceeds 1ms"
    print("✅ Performance test passed (< 1ms)!\n")


if __name__ == "__main__":
    test_crisis_detection()
    test_performance()
    print("🎉 All quick tests passed!")
