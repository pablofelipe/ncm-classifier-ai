"""Etapa 7 hardening: CORS, security headers, and a request-body size cap.

All three are cross-cutting, registered once in src/main.py — no domain
logic, no adapter wiring, pure HTTP concerns (hexagonal-boundaries skill).
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)


# ---------------------------------------------------------------------------
# CORS: a public demo API with no cookies/session state (ADR-0015 — "anyone
# can try it") — a wildcard origin carries no credential-leak risk here.
# ---------------------------------------------------------------------------


def test_cors_preflight_allows_any_origin(client: TestClient) -> None:
    response = client.options(
        "/classify",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "*"


def test_cors_preflight_allows_the_byok_headers(client: TestClient) -> None:
    response = client.options(
        "/classify",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-llm-api-key",
        },
    )
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-llm-api-key" in allowed


# ---------------------------------------------------------------------------
# Security headers — cheap, no-downside defense-in-depth for a stateless
# JSON API (no HTML rendering, so CSP is not applicable and is skipped).
# ---------------------------------------------------------------------------


def test_response_sets_nosniff_header(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_response_sets_frame_deny_header(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["x-frame-options"] == "DENY"


def test_response_sets_referrer_policy_header(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["referrer-policy"] == "no-referrer"


def test_response_sets_hsts_header(client: TestClient) -> None:
    response = client.get("/health")
    assert "max-age" in response.headers["strict-transport-security"]


# ---------------------------------------------------------------------------
# Payload size cap: Pydantic's max_length (schemas.py) only rejects an
# oversized field *after* the whole body is read into memory — this middleware
# rejects a declared oversized body before that ever happens.
# ---------------------------------------------------------------------------


def test_rejects_oversized_request_body(client: TestClient) -> None:
    huge_description = "x" * 20_000
    response = client.post(
        "/classify",
        content=f'{{"product_name": "a", "description": "{huge_description}"}}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_accepts_a_normal_sized_request_body(client: TestClient) -> None:
    response = client.post(
        "/classify",
        json={"product_name": "agua mineral", "description": "garrafa 500ml"},
    )
    assert response.status_code != 413
