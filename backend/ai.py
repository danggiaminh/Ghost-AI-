from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

TIER_LIGHT = "tier_light"
TIER_STANDARD = "tier_standard"
TIER_REASONING = "tier_reasoning"
TIER_VISION = "tier_vision"

INTENT_CASUAL_CHAT = "casual_chat"
INTENT_KNOWLEDGE_QUESTION = "knowledge_question"
INTENT_CODING_TASK = "coding_task"
INTENT_DEBUGGING = "debugging"
INTENT_IMAGE_ANALYSIS = "image_analysis"
INTENT_EMOTIONAL_SUPPORT = "emotional_support"
INTENT_UNKNOWN = "unknown"

STRONG_TIERS = {TIER_REASONING, TIER_VISION}

GREETING_PATTERN = re.compile(r"\b(hi|hello|hey|yo|good morning|good evening|sup|thanks|thank you)\b", re.IGNORECASE)
KNOWLEDGE_PATTERN = re.compile(r"\b(what|why|how|explain|difference|define|learn|tutorial|guide|concept)\b", re.IGNORECASE)
CODING_PATTERN = re.compile(r"\b(code|function|api|algorithm|class|python|javascript|typescript|sql|react|fastapi|refactor|implement)\b", re.IGNORECASE)
DEBUG_PATTERN = re.compile(r"\b(debug|bug|error|traceback|stack|exception|crash|failing|failure|fix|log)\b", re.IGNORECASE)
IMAGE_PATTERN = re.compile(r"\b(image|photo|screenshot|picture|diagram|scan|ocr|visual)\b", re.IGNORECASE)
EMOTIONAL_PATTERN = re.compile(r"\b(sad|anxious|depressed|lonely|stressed|panic|overwhelmed|grief|burnout)\b", re.IGNORECASE)

LOGGER = logging.getLogger("ghost.amo")


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    model_tier: str
    message_length: int
    decision_ms: float
    downgraded: bool
    reason: str | None


@dataclass(frozen=True)
class ResponseEnvelope:
    text: str
    route: RouteDecision
    response_ms: float
    fallback_used: bool


class AdaptiveModelOptimizer:
    def __init__(
        self,
        max_consecutive_strong: int = 3,
        spike_threshold: int = 10,
        spike_window_seconds: int = 60,
    ) -> None:
        self._max_consecutive_strong = max_consecutive_strong
        self._spike_threshold = spike_threshold
        self._spike_window_seconds = spike_window_seconds
        self._consecutive_strong = 0
        self._strong_requests: deque[float] = deque()
        self._lock = Lock()

    def route(self, message: str, has_image: bool = False) -> RouteDecision:
        start = time.perf_counter_ns()
        normalized = (message or "").strip()
        message_length = len(normalized)
        reason = None
        downgraded = False

        try:
            intent = detect_intent(normalized)
            if has_image:
                intent = INTENT_IMAGE_ANALYSIS

            selected_tier = select_model(intent, message_length)
            now = time.monotonic()

            with self._lock:
                self._expire_old_spike_events(now)

                if selected_tier in STRONG_TIERS:
                    if self._consecutive_strong >= self._max_consecutive_strong:
                        selected_tier = TIER_STANDARD
                        downgraded = True
                        reason = "consecutive_strong_limit"
                    elif len(self._strong_requests) >= self._spike_threshold:
                        selected_tier = TIER_STANDARD
                        downgraded = True
                        reason = "usage_spike"

                if selected_tier in STRONG_TIERS:
                    self._consecutive_strong += 1
                    self._strong_requests.append(now)
                else:
                    self._consecutive_strong = 0
        except Exception:
            intent = INTENT_UNKNOWN
            selected_tier = TIER_STANDARD
            reason = "routing_failure"

        decision_ms = (time.perf_counter_ns() - start) / 1_000_000
        decision = RouteDecision(
            intent=intent,
            model_tier=selected_tier,
            message_length=message_length,
            decision_ms=decision_ms,
            downgraded=downgraded,
            reason=reason,
        )

        LOGGER.info(
            "amo.route intent=%s tier=%s decision_ms=%.3f downgraded=%s reason=%s",
            decision.intent,
            decision.model_tier,
            decision.decision_ms,
            decision.downgraded,
            decision.reason,
        )
        return decision

    def failsafe_decision(self, message: str, reason: str) -> RouteDecision:
        return RouteDecision(
            intent=detect_intent(message or ""),
            model_tier=TIER_STANDARD,
            message_length=len((message or "").strip()),
            decision_ms=0.0,
            downgraded=False,
            reason=reason,
        )

    def _expire_old_spike_events(self, now: float) -> None:
        threshold = now - self._spike_window_seconds
        while self._strong_requests and self._strong_requests[0] < threshold:
            self._strong_requests.popleft()


def detect_intent(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return INTENT_UNKNOWN

    if IMAGE_PATTERN.search(text):
        return INTENT_IMAGE_ANALYSIS

    if DEBUG_PATTERN.search(text):
        return INTENT_DEBUGGING

    if CODING_PATTERN.search(text):
        return INTENT_CODING_TASK

    if EMOTIONAL_PATTERN.search(text):
        return INTENT_EMOTIONAL_SUPPORT

    if len(text) <= 60 and GREETING_PATTERN.search(text):
        return INTENT_CASUAL_CHAT

    if KNOWLEDGE_PATTERN.search(text) or text.endswith("?"):
        return INTENT_KNOWLEDGE_QUESTION

    if len(text.split()) <= 10 and GREETING_PATTERN.search(text):
        return INTENT_CASUAL_CHAT

    return INTENT_UNKNOWN


def select_model(intent: str, message_length: int) -> str:
    if message_length > 2000:
        return TIER_REASONING

    if intent == INTENT_CASUAL_CHAT:
        return TIER_LIGHT

    if intent == INTENT_KNOWLEDGE_QUESTION:
        return TIER_STANDARD

    if intent in {INTENT_CODING_TASK, INTENT_DEBUGGING}:
        return TIER_REASONING

    if intent == INTENT_IMAGE_ANALYSIS:
        return TIER_VISION

    if intent == INTENT_EMOTIONAL_SUPPORT:
        return TIER_STANDARD

    return TIER_STANDARD


async def generate_ai_response(
    message: str,
    image_context: dict | None,
    optimizer: AdaptiveModelOptimizer,
    route: RouteDecision | None = None,
) -> ResponseEnvelope:
    has_image = bool(image_context)
    selected_route = route or optimizer.route(message=message, has_image=has_image)

    start = time.perf_counter_ns()
    fallback_used = False
    try:
        response_text = await _provider_generate(
            model_tier=selected_route.model_tier,
            message=message,
            image_context=image_context,
            intent=selected_route.intent,
        )
    except Exception:
        fallback_used = True
        try:
            response_text = await _provider_generate(
                model_tier=TIER_STANDARD,
                message=message,
                image_context=image_context,
                intent=selected_route.intent,
                force_stable=True,
            )
        except Exception:
            response_text = "Ghost fallback: assistant core is online. Please retry in a moment."

    response_ms = (time.perf_counter_ns() - start) / 1_000_000
    return ResponseEnvelope(
        text=response_text,
        route=selected_route,
        response_ms=response_ms,
        fallback_used=fallback_used,
    )


async def _provider_generate(
    model_tier: str,
    message: str,
    image_context: dict | None,
    intent: str,
    force_stable: bool = False,
) -> str:
    if model_tier == TIER_LIGHT:
        await asyncio.sleep(0.02)
    elif model_tier == TIER_STANDARD:
        await asyncio.sleep(0.04)
    elif model_tier == TIER_REASONING:
        await asyncio.sleep(0.07)
    elif model_tier == TIER_VISION:
        await asyncio.sleep(0.08)
    else:
        await asyncio.sleep(0.04)

    if not force_stable and random.random() < 0.01:
        raise RuntimeError("provider transient failure")

    normalized = " ".join((message or "").split()).strip()

    if intent == INTENT_DEBUGGING:
        body = "Technical assistant mode enabled. Share logs, expected behavior, and minimal reproduction steps. "
    elif intent == INTENT_CODING_TASK:
        body = "Implementation mode enabled. I will provide concise and reliable coding guidance. "
    elif intent == INTENT_IMAGE_ANALYSIS or image_context:
        body = "Image analysis mode enabled. I can inspect text, structure, and visible anomalies from the upload. "
    elif intent == INTENT_EMOTIONAL_SUPPORT:
        body = "Support mode enabled. I will keep guidance calm, practical, and non-judgmental. "
    elif intent == INTENT_CASUAL_CHAT:
        body = "Light conversation mode enabled. "
    else:
        body = "Standard assistance mode enabled. "

    if normalized:
        return f"Ghost is active. {body}Focus: \"{normalized[:180]}\"."
    return "Ghost is active. Standard assistance mode enabled. Share your task and constraints."
