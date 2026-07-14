# Rate limiting (Etapa 7, ADR-0015 API hardening). Pure HTTP/adapter concern —
# no domain logic, never touches core/.
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.config import settings


class RateLimiter:
    """Fixed-window in-memory rate limiter, keyed by an arbitrary string (the
    client IP in production).

    In-memory and per-process by design: the public deployment (ADR-0015) is
    a single scale-to-zero Fly.io machine, not a fleet behind a shared store
    — a distributed limiter (Redis, etc.) would solve a problem this
    deployment doesn't have. `clock` is injectable so tests never sleep for
    real.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock if clock is not None else time.monotonic
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        window_start, count = self._buckets.get(key, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        if count >= self._max_requests:
            self._buckets[key] = (window_start, count)
            return False
        self._buckets[key] = (window_start, count + 1)
        return True


# Process-wide singleton for production use — see class docstring for why a
# single shared instance (not a fresh one per request) is the point.
_default_limiter = RateLimiter(max_requests=settings.rate_limit_per_minute, window_seconds=60.0)


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency provider — overridden in tests with an isolated
    RateLimiter instance so tests never share state with each other or with
    the real process-wide limiter."""
    return _default_limiter


def enforce_rate_limit(
    request: Request,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded — try again shortly.",
            headers={"Retry-After": str(int(limiter.window_seconds))},
        )
