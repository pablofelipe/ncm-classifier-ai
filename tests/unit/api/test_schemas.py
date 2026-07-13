import pytest
from pydantic import ValidationError

from src.api.schemas import ClassifyResponse, NCMCandidate


def _candidates(n: int) -> list[NCMCandidate]:
    return [
        NCMCandidate(ncm=f"2201.10.{i:02d}", description=f"bebida {i}", score=0.0) for i in range(n)
    ]


@pytest.mark.parametrize("n", [0, 1, 2, 4])
def test_response_rejects_candidates_not_length_three(n: int) -> None:
    with pytest.raises(ValidationError):
        ClassifyResponse(
            confidence_label="needs_review",
            candidates=_candidates(n),
            latency_ms=1.0,
        )


def test_response_accepts_three_candidates() -> None:
    response = ClassifyResponse(
        confidence_label="needs_review",
        candidates=_candidates(3),
        latency_ms=1.0,
    )
    assert len(response.candidates) == 3


def test_response_escalation_reason_defaults_to_none() -> None:
    response = ClassifyResponse(
        confidence_label="high",
        candidates=_candidates(3),
        latency_ms=1.0,
    )
    assert response.escalation_reason is None


def test_response_escalation_reason_is_settable() -> None:
    response = ClassifyResponse(
        confidence_label="needs_review",
        candidates=_candidates(3),
        latency_ms=1.0,
        escalation_reason="code_not_found",
    )
    assert response.escalation_reason == "code_not_found"
