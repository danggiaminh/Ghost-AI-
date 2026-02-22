#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import statistics

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.ai import (
    INTENT_CASUAL_CHAT,
    INTENT_CODING_TASK,
    INTENT_DEBUGGING,
    INTENT_IMAGE_ANALYSIS,
    INTENT_KNOWLEDGE_QUESTION,
    TIER_LIGHT,
    TIER_REASONING,
    TIER_STANDARD,
    TIER_VISION,
    AdaptiveModelOptimizer,
    detect_intent,
    select_model,
)


def main() -> None:
    samples = [
        ("hi ghost", INTENT_CASUAL_CHAT, TIER_LIGHT, False),
        ("what is dependency injection?", INTENT_KNOWLEDGE_QUESTION, TIER_STANDARD, False),
        ("write python fastapi code for auth", INTENT_CODING_TASK, TIER_REASONING, False),
        ("debug traceback error in parser", INTENT_DEBUGGING, TIER_REASONING, False),
        ("analyze this image", INTENT_IMAGE_ANALYSIS, TIER_VISION, True),
    ]

    for message, expected_intent, expected_tier, has_image in samples:
        intent = detect_intent(message)
        if has_image:
            intent = INTENT_IMAGE_ANALYSIS
        assert intent == expected_intent, f"intent mismatch {message}: {intent}"
        tier = select_model(intent, len(message))
        assert tier == expected_tier, f"tier mismatch {message}: {tier}"

    long_message_tier = select_model(INTENT_KNOWLEDGE_QUESTION, 2500)
    assert long_message_tier == TIER_REASONING, "long message should route to reasoning"

    optimizer = AdaptiveModelOptimizer(max_consecutive_strong=3, spike_threshold=1000)
    r1 = optimizer.route("debug crash 1", has_image=False)
    r2 = optimizer.route("debug crash 2", has_image=False)
    r3 = optimizer.route("debug crash 3", has_image=False)
    r4 = optimizer.route("debug crash 4", has_image=False)
    assert r1.model_tier == TIER_REASONING
    assert r2.model_tier == TIER_REASONING
    assert r3.model_tier == TIER_REASONING
    assert r4.model_tier == TIER_STANDARD and r4.downgraded

    latency_optimizer = AdaptiveModelOptimizer()
    decision_ms = []
    for index in range(2000):
        result = latency_optimizer.route(f"debug request {index}", has_image=False)
        decision_ms.append(result.decision_ms)

    max_ms = max(decision_ms)
    avg_ms = statistics.fmean(decision_ms)
    p95_ms = sorted(decision_ms)[int(len(decision_ms) * 0.95)]

    assert max_ms < 5.0, f"routing too slow max_ms={max_ms:.4f}"

    print(
        f"AMO OK avg_ms={avg_ms:.4f} p95_ms={p95_ms:.4f} max_ms={max_ms:.4f}"
    )


if __name__ == "__main__":
    main()
