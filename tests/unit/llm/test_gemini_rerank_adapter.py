import json
import logging

import pytest

from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.core.ports import LLMRerankPort
from src.llm.gemini_client import ConfigurationError
from src.llm.gemini_rerank_adapter import GeminiRerankAdapter


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate_content(self, **kwargs) -> "_FakeResponse":
        return _FakeResponse(self._text)


class _FakeGeminiClient:
    """Synchronous test double: returns a preset text from generate_content."""

    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _NeverCalledModels:
    def generate_content(self, **kwargs) -> "_FakeResponse":
        raise AssertionError("generate_content must not be called for empty candidate list")


class _NeverCalledClient:
    def __init__(self) -> None:
        self.models = _NeverCalledModels()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cand(ncm: str, desc: str, score: float = 0.5) -> ClassificationCandidate:
    return ClassificationCandidate(ncm_code=ncm, description=desc, score=score)


def _query(name: str = "Chivas 12 anos", description: str = "uísque escocês 750ml") -> ProductQuery:
    return ProductQuery(product_name=name, description=description)


def _ranked_json(*ncm_codes: str) -> str:
    return json.dumps({"ranked": list(ncm_codes)})


# ---------------------------------------------------------------------------
# Reordering
# ---------------------------------------------------------------------------


def test_reorders_candidates_by_ranked_json() -> None:
    candidates = [
        _cand("22083020", "Uísques de malte escocês"),
        _cand("22084000", "Rum e outras aguardentes"),
        _cand("22082000", "Aguardentes de vinho"),
    ]
    adapter = GeminiRerankAdapter(
        client=_FakeGeminiClient(_ranked_json("22084000", "22082000", "22083020"))
    )
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["22084000", "22082000", "22083020"]


def test_top_ranked_ncm_placed_first() -> None:
    candidates = [_cand("22089000", "Outras bebidas"), _cand("22030010", "Cervejas de malte")]
    adapter = GeminiRerankAdapter(
        client=_FakeGeminiClient(_ranked_json("22030010", "22089000"))
    )
    result = adapter.rerank(_query(name="heineken lata"), candidates)
    assert result[0].ncm_code == "22030010"


# ---------------------------------------------------------------------------
# Preservation
# ---------------------------------------------------------------------------


def test_ncm_code_and_description_preserved_after_rerank() -> None:
    candidates = [_cand("22011000", "Água mineral natural")]
    adapter = GeminiRerankAdapter(client=_FakeGeminiClient(_ranked_json("22011000")))
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
    adapter = GeminiRerankAdapter(client=_FakeGeminiClient(_ranked_json("22011000")))
    result = adapter.rerank(_query(), [c])
    assert result[0].metadata == {"chapter": "22", "ipi_rate": "0"}


def test_unranked_candidates_appended_at_end() -> None:
    candidates = [_cand("A", "desc-a"), _cand("B", "desc-b"), _cand("C", "desc-c")]
    adapter = GeminiRerankAdapter(client=_FakeGeminiClient(_ranked_json("B")))
    result = adapter.rerank(_query(), candidates)
    assert result[0].ncm_code == "B"
    assert {c.ncm_code for c in result[1:]} == {"A", "C"}


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


def test_fallback_returns_original_order_on_invalid_json() -> None:
    candidates = [_cand("X", "x-desc"), _cand("Y", "y-desc")]
    adapter = GeminiRerankAdapter(client=_FakeGeminiClient("not json at all"))
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["X", "Y"]


def test_fallback_returns_original_order_on_missing_ranked_key() -> None:
    candidates = [_cand("X", "x-desc"), _cand("Y", "y-desc")]
    adapter = GeminiRerankAdapter(client=_FakeGeminiClient('{"wrong_key": []}'))
    result = adapter.rerank(_query(), candidates)
    assert [c.ncm_code for c in result] == ["X", "Y"]


def test_fallback_logs_malformed_response(caplog: pytest.LogCaptureFixture) -> None:
    raw = "não é json válido"
    adapter = GeminiRerankAdapter(client=_FakeGeminiClient(raw))
    with caplog.at_level(logging.WARNING, logger="src.llm.gemini_rerank_adapter"):
        adapter.rerank(_query(), [_cand("X", "x")])
    assert any(raw in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Configuration error
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.llm.gemini_rerank_adapter as mod

    def _no_key() -> None:
        raise ConfigurationError("GEMINI_API_KEY not set")

    monkeypatch.setattr(mod, "_client", _no_key)
    adapter = GeminiRerankAdapter()  # no injected client
    with pytest.raises(ConfigurationError):
        adapter.rerank(_query(), [_cand("X", "x")])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_candidates_returns_empty_list_without_calling_client() -> None:
    adapter = GeminiRerankAdapter(client=_NeverCalledClient())
    assert adapter.rerank(_query(), []) == []


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_implements_llm_rerank_port() -> None:
    assert isinstance(GeminiRerankAdapter(), LLMRerankPort)
