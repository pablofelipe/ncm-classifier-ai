from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.core.ports import LLMRerankPort
from src.llm.passthrough_adapter import PassthroughRerankAdapter


def _candidates() -> list[ClassificationCandidate]:
    return [
        ClassificationCandidate(ncm_code="2201.10.00", description="a", score=0.0),
        ClassificationCandidate(ncm_code="2202.10.00", description="b", score=0.0),
        ClassificationCandidate(ncm_code="2203.00.00", description="c", score=0.0),
    ]


def _query() -> ProductQuery:
    return ProductQuery(product_name="cerveja", description="lata 350ml")


def test_returns_candidates_unchanged() -> None:
    candidates = _candidates()
    result = PassthroughRerankAdapter().rerank(_query(), candidates)
    assert result == candidates


def test_preserves_order() -> None:
    candidates = _candidates()
    result = PassthroughRerankAdapter().rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == [c.ncm_code for c in candidates]


def test_implements_llm_rerank_port() -> None:
    assert isinstance(PassthroughRerankAdapter(), LLMRerankPort)
