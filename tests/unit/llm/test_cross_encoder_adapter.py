import pytest

from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.core.ports import LLMRerankPort
from src.llm.cross_encoder_adapter import CrossEncoderRerankAdapter


class _FakeEncoder:
    """Deterministic mock: returns predefined scores keyed by passage text."""

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._scores.get(passage, 0.0) for _, passage in pairs]


class _CapturingEncoder:
    """Records the pairs passed to predict; returns 0.0 for each."""

    def __init__(self) -> None:
        self.captured: list[list[tuple[str, str]]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.captured.append(pairs)
        return [0.0] * len(pairs)


def _cand(ncm: str, desc: str, score: float = 0.5) -> ClassificationCandidate:
    return ClassificationCandidate(ncm_code=ncm, description=desc, score=score)


def _query(name: str = "Chivas 12 anos", description: str = "uísque escocês 750ml") -> ProductQuery:
    return ProductQuery(product_name=name, description=description)


# ---------------------------------------------------------------------------
# Reordering
# ---------------------------------------------------------------------------


def test_reorders_candidates_by_cross_encoder_score_descending() -> None:
    scores = {
        "uísque escocês": 2.5,
        "cachaça artesanal": 0.1,
        "cerveja de malte": 1.3,
    }
    candidates = [
        _cand("2208.30.00", "uísque escocês"),
        _cand("2208.40.00", "cachaça artesanal"),
        _cand("2203.00.00", "cerveja de malte"),
    ]
    adapter = CrossEncoderRerankAdapter(encoder=_FakeEncoder(scores))
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["2208.30.00", "2203.00.00", "2208.40.00"]


def test_score_reflects_cross_encoder_logit() -> None:
    scores = {"aguardente de cana": 3.7}
    candidates = [_cand("2208.40.00", "aguardente de cana")]
    adapter = CrossEncoderRerankAdapter(encoder=_FakeEncoder(scores))
    result = adapter.rerank(_query(), candidates)
    assert result[0].score == pytest.approx(3.7)


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------


def test_ncm_code_and_description_preserved_after_rerank() -> None:
    candidates = [_cand("2201.10.00", "agua mineral")]
    adapter = CrossEncoderRerankAdapter(encoder=_FakeEncoder({}))
    result = adapter.rerank(_query(), candidates)
    assert result[0].ncm_code == "2201.10.00"
    assert result[0].description == "agua mineral"


def test_metadata_preserved_after_rerank() -> None:
    c = ClassificationCandidate(
        ncm_code="2201.10.00",
        description="agua mineral",
        score=0.5,
        metadata={"chapter": "22", "ipi_rate": "0"},
    )
    adapter = CrossEncoderRerankAdapter(encoder=_FakeEncoder({}))
    result = adapter.rerank(_query(), [c])
    assert result[0].metadata == {"chapter": "22", "ipi_rate": "0"}


# ---------------------------------------------------------------------------
# Query text format
# ---------------------------------------------------------------------------


def test_query_text_combines_product_name_and_description() -> None:
    enc = _CapturingEncoder()
    adapter = CrossEncoderRerankAdapter(encoder=enc)
    adapter.rerank(_query(name="Chivas 12", description="750ml"), [_cand("X", "p")])
    assert enc.captured[0][0][0] == "Chivas 12 750ml"


def test_query_text_uses_name_only_when_description_is_empty() -> None:
    enc = _CapturingEncoder()
    adapter = CrossEncoderRerankAdapter(encoder=enc)
    adapter.rerank(_query(name="cerveja", description=""), [_cand("X", "p")])
    assert enc.captured[0][0][0] == "cerveja"


def test_passage_is_candidate_description() -> None:
    enc = _CapturingEncoder()
    adapter = CrossEncoderRerankAdapter(encoder=enc)
    adapter.rerank(_query(), [_cand("X", "vodca premium")])
    assert enc.captured[0][0][1] == "vodca premium"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_candidates_returns_empty_list() -> None:
    adapter = CrossEncoderRerankAdapter(encoder=_FakeEncoder({}))
    assert adapter.rerank(_query(), []) == []


def test_single_candidate_returned_unchanged_in_content() -> None:
    c = _cand("2208.60.00", "vodca")
    adapter = CrossEncoderRerankAdapter(encoder=_FakeEncoder({"vodca": 1.0}))
    result = adapter.rerank(_query(), [c])
    assert len(result) == 1
    assert result[0].ncm_code == "2208.60.00"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_implements_llm_rerank_port() -> None:
    assert isinstance(CrossEncoderRerankAdapter(encoder=_FakeEncoder({})), LLMRerankPort)
