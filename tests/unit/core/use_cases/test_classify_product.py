import pytest

from src.core.domain.ncm import ClassificationCandidate, NCMCode, ProductQuery
from src.core.use_cases.classify_product import ClassifyProduct
from src.core.verification.deterministic import TIPIIndex

# --- Local fakes implementing the Protocols structurally (no Naive/Passthrough) ---


class FakeRetrieval:
    def __init__(self, to_return: list[ClassificationCandidate]) -> None:
        self._to_return = to_return
        self.calls: list[int] = []

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
        self.calls.append(k)
        return self._to_return


class FakeRerank:
    def __init__(self, to_return: list[ClassificationCandidate] | None = None) -> None:
        self._to_return = to_return
        self.received: list[ClassificationCandidate] | None = None

    def rerank(
        self, query: ProductQuery, candidates: list[ClassificationCandidate]
    ) -> list[ClassificationCandidate]:
        self.received = candidates
        return self._to_return if self._to_return is not None else candidates


def _query() -> ProductQuery:
    return ProductQuery(product_name="agua mineral", description="garrafa 500ml")


def _candidates(*scores: float) -> list[ClassificationCandidate]:
    return [
        ClassificationCandidate(ncm_code=f"2201.10.{i:02d}", description=f"bebida {i}", score=s)
        for i, s in enumerate(scores)
    ]


def _use_case(
    retrieved: list[ClassificationCandidate],
    *,
    rerank: FakeRerank | None = None,
    threshold: float = 0.5,
    verification: TIPIIndex | None = None,
) -> tuple[ClassifyProduct, FakeRetrieval, FakeRerank]:
    fake_retrieval = FakeRetrieval(retrieved)
    fake_rerank = rerank if rerank is not None else FakeRerank()
    uc = ClassifyProduct(
        fake_retrieval,
        fake_rerank,
        confidence_threshold=threshold,
        verification=verification,
    )
    return uc, fake_retrieval, fake_rerank


# --- Constructor validation ---


def test_constructor_rejects_threshold_below_zero() -> None:
    with pytest.raises(ValueError):
        ClassifyProduct(FakeRetrieval([]), FakeRerank(), confidence_threshold=-0.1)


def test_constructor_rejects_threshold_above_one() -> None:
    with pytest.raises(ValueError):
        ClassifyProduct(FakeRetrieval([]), FakeRerank(), confidence_threshold=1.1)


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_constructor_accepts_threshold_at_boundaries(threshold: float) -> None:
    uc = ClassifyProduct(FakeRetrieval([]), FakeRerank(), confidence_threshold=threshold)
    assert uc is not None


# --- Orchestration ---


def test_execute_calls_retrieval_with_k_10() -> None:
    uc, fake_retrieval, _ = _use_case(_candidates(0.0, 0.0, 0.0))
    uc.execute(_query())
    assert fake_retrieval.calls == [10]


def test_execute_passes_retrieved_candidates_to_rerank() -> None:
    retrieved = _candidates(0.0, 0.0, 0.0)
    uc, _, fake_rerank = _use_case(retrieved)
    uc.execute(_query())
    assert fake_rerank.received == retrieved


def test_execute_returns_top_3_after_rerank() -> None:
    reranked = _candidates(0.0, 0.0, 0.0)
    uc, _, _ = _use_case(_candidates(0.0, 0.0, 0.0), rerank=FakeRerank(reranked))
    result = uc.execute(_query())
    assert result.top_candidates == reranked


def test_execute_returns_top_3_even_when_rerank_returns_more() -> None:
    reranked = _candidates(0.0, 0.0, 0.0, 0.0, 0.0)
    uc, _, _ = _use_case(_candidates(0.0, 0.0, 0.0), rerank=FakeRerank(reranked))
    result = uc.execute(_query())
    assert result.top_candidates == reranked[:3]


# --- Confidence gating ---


def test_execute_high_confidence_when_top_score_meets_threshold() -> None:
    uc, _, _ = _use_case(_candidates(0.8, 0.1, 0.0), threshold=0.5)
    result = uc.execute(_query())
    assert result.confidence_label == "high"


def test_execute_needs_review_when_top_score_below_threshold() -> None:
    uc, _, _ = _use_case(_candidates(0.3, 0.1, 0.0), threshold=0.5)
    result = uc.execute(_query())
    assert result.confidence_label == "needs_review"


def test_execute_needs_review_when_top_score_exactly_zero() -> None:
    uc, _, _ = _use_case(_candidates(0.0, 0.0, 0.0), threshold=0.5)
    result = uc.execute(_query())
    assert result.confidence_label == "needs_review"


# --- Verification gate (ADR-0014) ---


def _tipi_index() -> TIPIIndex:
    return TIPIIndex(
        {
            NCMCode("2201.10.00"): {
                "chapter": "22",
                "heading": "22.01",
                "description": "agua mineral",
            },
        }
    )


def _candidate_with_code(ncm_code: str, score: float) -> ClassificationCandidate:
    return ClassificationCandidate(ncm_code=ncm_code, description="bebida", score=score)


def _three_candidates_with_top(top_code: str, top_score: float) -> list[ClassificationCandidate]:
    return [
        _candidate_with_code(top_code, top_score),
        _candidate_with_code("2202.10.01", 0.1),
        _candidate_with_code("2202.10.02", 0.0),
    ]


def test_execute_without_verification_gates_purely_by_score() -> None:
    candidates = _three_candidates_with_top("9999.99.99", 0.8)
    uc, _, _ = _use_case(candidates, threshold=0.5, verification=None)
    result = uc.execute(_query())
    assert result.confidence_label == "high"


def test_execute_without_verification_escalation_reason_is_none() -> None:
    uc, _, _ = _use_case(_candidates(0.8, 0.1, 0.0), threshold=0.5, verification=None)
    result = uc.execute(_query())
    assert result.escalation_reason is None


def test_execute_with_verification_passing_top_candidate_gates_by_score() -> None:
    candidates = _three_candidates_with_top("2201.10.00", 0.8)
    uc, _, _ = _use_case(candidates, threshold=0.5, verification=_tipi_index())
    result = uc.execute(_query())
    assert result.confidence_label == "high"


def test_execute_with_verification_passing_top_candidate_escalation_reason_is_none() -> None:
    candidates = _three_candidates_with_top("2201.10.00", 0.8)
    uc, _, _ = _use_case(candidates, threshold=0.5, verification=_tipi_index())
    result = uc.execute(_query())
    assert result.escalation_reason is None


def test_execute_with_verification_failing_top_candidate_forces_needs_review() -> None:
    # Score is well above threshold, but the top NCM doesn't exist in the index.
    candidates = _three_candidates_with_top("9999.99.99", 0.9)
    uc, _, _ = _use_case(candidates, threshold=0.5, verification=_tipi_index())
    result = uc.execute(_query())
    assert result.confidence_label == "needs_review"


def test_execute_with_verification_failing_top_candidate_sets_escalation_reason() -> None:
    candidates = _three_candidates_with_top("9999.99.99", 0.9)
    uc, _, _ = _use_case(candidates, threshold=0.5, verification=_tipi_index())
    result = uc.execute(_query())
    assert result.escalation_reason == "code_not_found"


def test_execute_with_verification_failing_top_candidate_keeps_same_top_candidates() -> None:
    candidates = _three_candidates_with_top("9999.99.99", 0.9)
    uc, _, _ = _use_case(candidates, threshold=0.5, verification=_tipi_index())
    result = uc.execute(_query())
    assert result.top_candidates == candidates
