from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


@dataclass
class RateRule:
    limit: int
    window_seconds: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, rule: RateRule) -> tuple[bool, int]:
        now = time.time()
        async with self._lock:
            queue = self._events[key]
            boundary = now - rule.window_seconds
            while queue and queue[0] < boundary:
                queue.popleft()
            if len(queue) >= rule.limit:
                retry_after = int(max(1, rule.window_seconds - (now - queue[0])))
                return False, retry_after
            queue.append(now)
            return True, 0


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: InMemoryRateLimiter):
        super().__init__(app)
        self._limiter = limiter
        self._default_rule = RateRule(limit=240, window_seconds=60)
        self._chat_rule = RateRule(limit=45, window_seconds=60)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
        request.state.client_ip = client_ip.split(",")[0].strip()

        path = request.url.path
        rule = self._chat_rule if path.startswith("/chat") else self._default_rule
        allowed, retry_after = await self._limiter.allow(f"{request.state.client_ip}:{path}", rule)
        if not allowed:
            return JSONResponse(
                {"error": True, "message": f"Rate limit exceeded. Retry in {retry_after}s"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        raw_body = await request.body()
        last_message = ""
        if raw_body:
            try:
                decoded = json.loads(raw_body.decode("utf-8"))
                if isinstance(decoded, dict):
                    possible_message = decoded.get("message")
                    if isinstance(possible_message, str):
                        last_message = possible_message[:500]
            except Exception:
                pass

        request.state.last_user_message = last_message

        async def receive_once():
            return {"type": "http.request", "body": raw_body, "more_body": False}

        request = Request(request.scope, receive_once)
        request.state.client_ip = client_ip.split(",")[0].strip()
        request.state.last_user_message = last_message

        return await call_next(request)
