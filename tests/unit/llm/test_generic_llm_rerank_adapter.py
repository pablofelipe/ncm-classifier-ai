import json
import logging

import pytest

from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.core.ports import LLMRerankPort
from src.llm.generic_llm_rerank_adapter import GenericLLMRerankAdapter

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeLLMClient:
    """Synchronous test double: returns a preset text from generate()."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def generate(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self._text


class _NeverCalledLLMClient:
    def generate(self, **kwargs) -> str:
        raise AssertionError("generate must not be called for empty candidate list")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cand(ncm: str, desc: str, score: float = 0.5) -> ClassificationCandidate:
    return ClassificationCandidate(ncm_code=ncm, description=desc, score=score)


def _query(name: str = "Chivas 12 anos", description: str = "uísque escocês 750ml") -> ProductQuery:
    return ProductQuery(product_name=name, description=description)


def _ranked_json(*ncm_codes: str) -> str:
    return json.dumps({"ranked": list(ncm_codes)})


def _adapter(
    text: str, model: str = "gemini-2.5-flash"
) -> tuple[GenericLLMRerankAdapter, _FakeLLMClient]:
    client = _FakeLLMClient(text)
    return GenericLLMRerankAdapter(client, model=model), client


# ---------------------------------------------------------------------------
# Reordering
# ---------------------------------------------------------------------------


def test_reorders_candidates_by_ranked_json() -> None:
    candidates = [
        _cand("22083020", "Uísques de malte escocês"),
        _cand("22084000", "Rum e outras aguardentes"),
        _cand("22082000", "Aguardentes de vinho"),
    ]
    adapter, _ = _adapter(_ranked_json("22084000", "22082000", "22083020"))
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["22084000", "22082000", "22083020"]


def test_top_ranked_ncm_placed_first() -> None:
    candidates = [_cand("22089000", "Outras bebidas"), _cand("22030010", "Cervejas de malte")]
    adapter, _ = _adapter(_ranked_json("22030010", "22089000"))
    result = adapter.rerank(_query(name="heineken lata"), candidates)
    assert result[0].ncm_code == "22030010"


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------


def test_ncm_code_and_description_preserved_after_rerank() -> None:
    candidates = [_cand("22011000", "Água mineral natural")]
    adapter, _ = _adapter(_ranked_json("22011000"))
    result = adapter.rerank(_query(), candidates)
    assert result[0].ncm_code == "22011000"
    assert result[0].description == "Água mineral natural"


def test_metadata_preserved_after_rerank() -> None:
    c = ClassificationCandidate(
        ncm_code="22011000",
        description="Água mineral",
        score=0.5,
        metadata={"chapter": "22", "ipi_rate": "0"},
    )
    adapter, _ = _adapter(_ranked_json("22011000"))
    result = adapter.rerank(_query(), [c])
    assert result[0].metadata == {"chapter": "22", "ipi_rate": "0"}


def test_unranked_candidates_appended_at_end() -> None:
    candidates = [_cand("A", "desc-a"), _cand("B", "desc-b"), _cand("C", "desc-c")]
    adapter, _ = _adapter(_ranked_json("B"))
    result = adapter.rerank(_query(), candidates)
    assert result[0].ncm_code == "B"
    assert {c.ncm_code for c in result[1:]} == {"A", "C"}


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


def test_fallback_returns_original_order_on_invalid_json() -> None:
    candidates = [_cand("X", "x-desc"), _cand("Y", "y-desc")]
    adapter, _ = _adapter("not json at all")
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["X", "Y"]


def test_fallback_returns_original_order_on_missing_ranked_key() -> None:
    candidates = [_cand("X", "x-desc"), _cand("Y", "y-desc")]
    adapter, _ = _adapter('{"wrong_key": []}')
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["X", "Y"]


def test_fallback_logs_malformed_response(caplog: pytest.LogCaptureFixture) -> None:
    raw = "não é json válido"
    adapter, _ = _adapter(raw)
    with caplog.at_level(logging.WARNING, logger="src.llm.generic_llm_rerank_adapter"):
        adapter.rerank(_query(), [_cand("X", "x")])
    assert any(raw in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# LLMClient.generate() call shape
# ---------------------------------------------------------------------------


def test_model_is_forwarded_unchanged_to_generate() -> None:
    adapter, client = _adapter(_ranked_json("X"), model="gemini-2.5-pro")
    adapter.rerank(_query(), [_cand("X", "x")])
    assert client.calls[0]["model"] == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_candidates_returns_empty_list_without_calling_client() -> None:
    adapter = GenericLLMRerankAdapter(_NeverCalledLLMClient(), model="gemini-2.5-flash")
    assert adapter.rerank(_query(), []) == []


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_implements_llm_rerank_port() -> None:
    adapter = GenericLLMRerankAdapter(_FakeLLMClient(_ranked_json()), model="gemini-2.5-flash")
    assert isinstance(adapter, LLMRerankPort)
