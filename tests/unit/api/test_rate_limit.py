"""Etapa 7 hardening: in-memory per-IP rate limiting on POST /classify only —
GET /health (Fly.io's own health check probe) must never be throttled."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_classify_use_case
from src.api.rate_limit import RateLimiter, get_rate_limiter
from src.core.domain.ncm import ClassificationCandidate, ClassificationResult, NCMCode
from src.main import app


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------------
# RateLimiter — pure unit tests, no FastAPI, deterministic fake clock.
# ---------------------------------------------------------------------------


def test_allows_requests_up_to_the_limit() -> None:
    limiter = RateLimiter(max_requests=3, window_seconds=60.0, clock=_FakeClock())
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True


def test_rejects_the_request_beyond_the_limit_within_the_window() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60.0, clock=_FakeClock())
    limiter.allow("1.2.3.4")
    limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4") is False


def test_resets_after_the_window_elapses() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
    limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4") is False
    clock.advance(61.0)
    assert limiter.allow("1.2.3.4") is True


def test_tracks_different_keys_independently() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=_FakeClock())
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("5.6.7.8") is True


# ---------------------------------------------------------------------------
# Wired into POST /classify via Depends(enforce_rate_limit) — route-level,
# dependency-overridden for isolation from the real process-wide limiter.
# ---------------------------------------------------------------------------


class _FakeClassifyUseCase:
    def execute(self, query: object) -> ClassificationResult:
        candidates = [
            ClassificationCandidate(
                ncm_code=NCMCode(f"2201.10.{i:02d}"), description="x", score=0.0
            )
            for i in range(3)
        ]
        return ClassificationResult(top_candidates=candidates, confidence_label="needs_review")


def _valid_payload() -> dict[str, str]:
    return {"product_name": "agua mineral", "description": "garrafa 500ml"}


@pytest.fixture
def client_with_limit_one() -> Iterator[TestClient]:
    # The limiter is built once, outside the override lambda: FastAPI calls a
    # dependency override on every request (cached only within one request),
    # so returning `RateLimiter(...)` directly from the lambda would hand out
    # a fresh, empty limiter each call — never accumulating state.
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=_FakeClock())
    app.dependency_overrides[get_classify_use_case] = lambda: _FakeClassifyUseCase()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_classify_allows_the_first_request(client_with_limit_one: TestClient) -> None:
    response = client_with_limit_one.post("/classify", json=_valid_payload())
    assert response.status_code == 200


def test_classify_returns_429_after_limit_exceeded(client_with_limit_one: TestClient) -> None:
    client_with_limit_one.post("/classify", json=_valid_payload())
    response = client_with_limit_one.post("/classify", json=_valid_payload())
    assert response.status_code == 429


def test_classify_429_response_includes_retry_after_header(
    client_with_limit_one: TestClient,
) -> None:
    client_with_limit_one.post("/classify", json=_valid_payload())
    response = client_with_limit_one.post("/classify", json=_valid_payload())
    assert "Retry-After" in response.headers


def test_health_is_never_rate_limited(client_with_limit_one: TestClient) -> None:
    for _ in range(5):
        response = client_with_limit_one.get("/health")
        assert response.status_code == 200
