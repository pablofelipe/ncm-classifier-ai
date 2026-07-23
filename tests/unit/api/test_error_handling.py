"""Etapa 7 hardening: provider errors surface as clean HTTP responses, not an
unhandled 500 with a stack trace (ADR-0016 Consequences — known gap closed
here). Exercises the real exception_handler registered in src/main.py."""

from collections.abc import Iterator

from fastapi.testclient import TestClient

from src.api.dependencies import get_classify_use_case
from src.core.domain.ncm import ProductQuery
from src.llm.gemini_client import LLMProviderError
from src.main import app


class _RaisingUseCase:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def execute(self, query: ProductQuery) -> None:
        raise self._exc


def _client_raising(exc: Exception) -> Iterator[TestClient]:
    app.dependency_overrides[get_classify_use_case] = lambda: _RaisingUseCase(exc)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def _valid_payload() -> dict[str, str]:
    return {"product_name": "agua mineral", "description": "garrafa 500ml"}


def test_llm_provider_client_error_returns_422_not_500() -> None:
    gen = _client_raising(LLMProviderError(422, "LLM provider rejected the request."))
    client = next(gen)
    try:
        response = client.post("/classify", json=_valid_payload())
        assert response.status_code == 422
    finally:
        gen.close()


def test_llm_provider_server_error_returns_502_not_500() -> None:
    gen = _client_raising(LLMProviderError(502, "LLM provider is currently unavailable."))
    client = next(gen)
    try:
        response = client.post("/classify", json=_valid_payload())
        assert response.status_code == 502
    finally:
        gen.close()


def test_llm_provider_error_response_has_clean_detail_no_stack_trace() -> None:
    gen = _client_raising(LLMProviderError(422, "LLM provider rejected the request."))
    client = next(gen)
    try:
        response = client.post("/classify", json=_valid_payload())
        assert response.json() == {"detail": "LLM provider rejected the request."}
    finally:
        gen.close()
