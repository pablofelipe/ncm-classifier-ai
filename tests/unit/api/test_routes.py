from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_classify_use_case
from src.core.domain.ncm import (
    ClassificationCandidate,
    ClassificationResult,
    ConfidenceLabel,
    NCMCode,
)
from src.main import app


class FakeClassifyUseCase:
    """Stands in for ClassifyProduct so route tests avoid loading TIPI JSON."""

    def __init__(
        self, label: ConfidenceLabel = "needs_review", escalation_reason: str | None = None
    ) -> None:
        self._label = label
        self._escalation_reason = escalation_reason

    def execute(self, query: object) -> ClassificationResult:
        candidates = [
            ClassificationCandidate(
                ncm_code=NCMCode(f"2201.10.{i:02d}"), description=f"bebida {i}", score=0.0
            )
            for i in range(3)
        ]
        return ClassificationResult(
            top_candidates=candidates,
            confidence_label=self._label,
            escalation_reason=self._escalation_reason,
        )


def _override(
    label: ConfidenceLabel = "needs_review", escalation_reason: str | None = None
) -> Iterator[TestClient]:
    app.dependency_overrides[get_classify_use_case] = lambda: FakeClassifyUseCase(
        label, escalation_reason
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _override()


def _valid_payload() -> dict[str, str]:
    return {"product_name": "agua mineral", "description": "garrafa 500ml"}


def test_classify_returns_200_with_valid_request(client: TestClient) -> None:
    response = client.post("/classify", json=_valid_payload())
    assert response.status_code == 200


def test_classify_returns_three_candidates(client: TestClient) -> None:
    response = client.post("/classify", json=_valid_payload())
    assert len(response.json()["candidates"]) == 3


def test_classify_returns_latency_ms_positive(client: TestClient) -> None:
    response = client.post("/classify", json=_valid_payload())
    assert response.json()["latency_ms"] > 0.0


def test_classify_returns_needs_review_when_top_score_below_threshold(
    client: TestClient,
) -> None:
    response = client.post("/classify", json=_valid_payload())
    assert response.json()["confidence_label"] == "needs_review"


def test_classify_rejects_request_missing_product_name(client: TestClient) -> None:
    response = client.post("/classify", json={"description": "garrafa 500ml"})
    assert response.status_code == 422


def test_classify_rejects_description_exceeding_max_length(client: TestClient) -> None:
    payload = {"product_name": "agua", "description": "x" * 301}
    response = client.post("/classify", json=payload)
    assert response.status_code == 422


def test_classify_returns_null_escalation_reason_by_default(client: TestClient) -> None:
    response = client.post("/classify", json=_valid_payload())
    assert response.json()["escalation_reason"] is None


def test_classify_returns_escalation_reason_from_use_case() -> None:
    gen = _override(label="needs_review", escalation_reason="code_not_found")
    client = next(gen)
    try:
        response = client.post("/classify", json=_valid_payload())
        assert response.json()["escalation_reason"] == "code_not_found"
    finally:
        gen.close()
