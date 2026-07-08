"""
SmartScrape Pro — Middleware & Rate Limiting
Request logging to DB, per-user rate limiting
"""
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from backend.utils.logger import logger


class APILoggingMiddleware(BaseHTTPMiddleware):
    """Log every API request to DB (async, non-blocking)."""

    SKIP_PATHS = {"/health", "/api/docs", "/api/redoc", "/api/openapi.json", "/"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000

        # Fire-and-forget DB log
        import asyncio
        asyncio.create_task(self._log_to_db(request, response, duration_ms))

        return response

    async def _log_to_db(self, request: Request, response: Response, duration_ms: float):
        try:
            from backend.models.database import AsyncSessionLocal
            from backend.models.models import APILog
            from backend.auth.security import decode_token

            user_id = None
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                payload = decode_token(auth[7:])
                if payload:
                    user_id = payload.get("sub")

            async with AsyncSessionLocal() as db:
                log = APILog(
                    user_id=user_id,
                    method=request.method,
                    endpoint=str(request.url.path),
                    status_code=response.status_code,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent", "")[:200],
                    response_time_ms=round(duration_ms, 2),
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.debug(f"API log write failed: {e}")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# ── Per-User In-Memory Rate Limiter ───────

from collections import defaultdict, deque
from threading import Lock

class InMemoryRateLimiter:
    """
    Sliding window rate limiter.
    Default: 60 req/min per IP.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._buckets[key]
            # Remove old entries outside window
            while bucket and bucket[0] < now - self.window:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = time.time()
        with self._lock:
            bucket = self._buckets[key]
            active = sum(1 for t in bucket if t >= now - self.window)
            return max(0, self.max_requests - active)


rate_limiter = InMemoryRateLimiter(max_requests=60, window_seconds=60)
