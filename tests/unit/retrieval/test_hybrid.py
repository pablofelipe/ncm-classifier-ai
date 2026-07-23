import pytest

from src.core.domain.ncm import ClassificationCandidate, NCMCode, ProductQuery
from src.core.ports import RetrievalPort
from src.retrieval.hybrid import HybridRetrievalAdapter

# RRF contribution for a hit at 0-based rank r with k=60: 1 / (60 + r + 1).
R0 = 1.0 / 61
R1 = 1.0 / 62

A, B, C = NCMCode("2201.10.01"), NCMCode("2201.10.02"), NCMCode("2201.10.03")


def _cand(ncm: NCMCode) -> ClassificationCandidate:
    return ClassificationCandidate(ncm_code=ncm, description=f"d-{ncm}", score=0.99)


class _FakePort:
    def __init__(self, candidates: list[ClassificationCandidate]) -> None:
        self._candidates = candidates

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
        return self._candidates[:k]


@pytest.fixture
def hybrid() -> HybridRetrievalAdapter:
    # dense: [A@0, B@1]  |  lexical: [B@0, C@1]
    dense = _FakePort([_cand(A), _cand(B)])
    lexical = _FakePort([_cand(B), _cand(C)])
    return HybridRetrievalAdapter(dense, lexical)


def _query() -> ProductQuery:
    return ProductQuery(product_name="x", description="")


def test_candidate_in_both_retrievers_ranks_first(hybrid: HybridRetrievalAdapter) -> None:
    # B is in both (dense@1 + lexical@0); it must outrank A and C.
    assert hybrid.retrieve_candidates(_query(), k=3)[0].ncm_code == B


def test_score_is_rrf_sum_for_candidate_in_both(hybrid: HybridRetrievalAdapter) -> None:
    by_ncm = {c.ncm_code: c for c in hybrid.retrieve_candidates(_query(), k=3)}
    assert by_ncm[B].score == pytest.approx(R1 + R0)


def test_candidate_only_in_dense_gets_rrf_score(hybrid: HybridRetrievalAdapter) -> None:
    # A appears only in dense at rank 0.
    by_ncm = {c.ncm_code: c for c in hybrid.retrieve_candidates(_query(), k=3)}
    assert by_ncm[A].score == pytest.approx(R0)


def test_candidate_only_in_lexical_gets_rrf_score(hybrid: HybridRetrievalAdapter) -> None:
    # C appears only in lexical at rank 1.
    by_ncm = {c.ncm_code: c for c in hybrid.retrieve_candidates(_query(), k=3)}
    assert by_ncm[C].score == pytest.approx(R1)


def test_fuses_duplicates_by_ncm_code(hybrid: HybridRetrievalAdapter) -> None:
    # B is returned by both retrievers but must appear once in the fused output.
    ncms = [c.ncm_code for c in hybrid.retrieve_candidates(_query(), k=3)]
    assert ncms.count(B) == 1


def test_respects_k_limit(hybrid: HybridRetrievalAdapter) -> None:
    assert len(hybrid.retrieve_candidates(_query(), k=2)) == 2


def test_implements_retrieval_port(hybrid: HybridRetrievalAdapter) -> None:
    assert isinstance(hybrid, RetrievalPort)
