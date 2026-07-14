"""Composition root tests (ADR-0004): build_classify_use_case wires the
Chroma retrieval adapter.

Uses an in-memory collection and a spy encoder — no real model, no persistent
client. The default (no-injection) path constructs the real PersistentClient
and is exercised by `make eval` / integration, not here.
"""

import json
from pathlib import Path
from uuid import uuid4

import chromadb
import pytest
from chromadb import Collection
from fastapi import HTTPException

from src.api.dependencies import _resolve_rerank_override, build_classify_use_case
from src.config import RerankMode, RetrievalMode, Settings, settings
from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.core.verification.deterministic import TIPIIndex
from src.llm.generic_llm_rerank_adapter import GenericLLMRerankAdapter
from src.llm.llm_client import resolve_llm_client
from src.retrieval.chroma_client import _find_latest_tipi_json, index_entries
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction, EmbedderModel
from src.retrieval.hierarchical import ChromaRetrievalAdapter
from src.retrieval.hybrid import HybridRetrievalAdapter


class SpyEncoder:
    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in sentences]


def _empty_collection() -> Collection:
    return chromadb.EphemeralClient().create_collection(
        name=f"deps_empty_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )


@pytest.fixture
def indexed_collection() -> Collection:
    entries = json.loads(
        _find_latest_tipi_json(Path("data/tipi"), "22").read_text(encoding="utf-8")
    )["entries"]
    collection = chromadb.EphemeralClient().create_collection(
        name=f"deps_indexed_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )
    index_entries(
        collection,
        entries,
        E5EmbeddingFunction(encoder=SpyEncoder()),
        EnrichStrategy.OFF,
        EmbedderModel.E5_SMALL,
    )
    return collection


def test_raises_actionable_error_when_index_is_empty() -> None:
    with pytest.raises(RuntimeError, match="make index"):
        build_classify_use_case(
            collection=_empty_collection(),
            embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
        )


def test_classifies_through_chroma_index_when_populated(
    indexed_collection: Collection,
) -> None:
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    result = use_case.execute(ProductQuery(product_name="cerveja", description=""))
    assert all(c.metadata["chapter"] == "22" for c in result.top_candidates)


# ---------------------------------------------------------------------------
# retrieval mode (ADR-0011): DENSE default keeps production unchanged; HYBRID
# wires BM25 + e5 fused by RRF. Selected at the composition root, no index change.
# ---------------------------------------------------------------------------


def test_retrieval_mode_defaults_to_dense() -> None:
    # No RETRIEVAL_MODE env var -> production stays dense-only.
    assert Settings().retrieval_mode is RetrievalMode.DENSE


def test_default_mode_wires_dense_only(indexed_collection: Collection) -> None:
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._retrieval, ChromaRetrievalAdapter)


def test_hybrid_mode_wires_hybrid_adapter(
    indexed_collection: Collection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "retrieval_mode", RetrievalMode.HYBRID)
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._retrieval, HybridRetrievalAdapter)


# ---------------------------------------------------------------------------
# verification gate (ADR-0014): the composition root builds a TIPIIndex from
# the same TIPI JSON used to populate the Chroma collection, and injects it
# into ClassifyProduct.
# ---------------------------------------------------------------------------


def test_wires_a_tipi_index_for_verification(indexed_collection: Collection) -> None:
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._verification, TIPIIndex)


def test_wired_verification_index_passes_a_real_indexed_ncm(
    indexed_collection: Collection,
) -> None:
    entries = json.loads(
        _find_latest_tipi_json(Path("data/tipi"), "22").read_text(encoding="utf-8")
    )["entries"]
    sample_dotless = entries[0]["ncm"].replace(".", "")

    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert use_case._verification is not None
    result = use_case._verification.verify(sample_dotless)
    assert result.passed


# ---------------------------------------------------------------------------
# LLM rerank provider resolution (ADR-0016): RERANK_MODE=gemini wires the
# generic, provider-agnostic adapter (not the retired Gemini-specific one).
# ---------------------------------------------------------------------------


def test_gemini_rerank_mode_wires_generic_llm_rerank_adapter(
    indexed_collection: Collection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rerank_mode", RerankMode.GEMINI)
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._rerank, GenericLLMRerankAdapter)


def test_gemini_rerank_mode_uses_resolved_client_and_configured_model(
    indexed_collection: Collection, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.api.dependencies as deps

    monkeypatch.setattr(settings, "rerank_mode", RerankMode.GEMINI)
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-pro")

    fake_client = object()
    monkeypatch.setattr(deps, "resolve_llm_client", lambda provider, api_key=None: fake_client)

    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert use_case._rerank._client is fake_client
    assert use_case._rerank._model == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# Per-request credential override (ADR-0016): X-LLM-Api-Key triggers building
# an ephemeral GenericLLMRerankAdapter for that one request only. No server
# credential (settings.gemini_api_key) is read on this path.
# ---------------------------------------------------------------------------


class _FakeRerankOverride:
    def rerank(
        self, query: ProductQuery, candidates: list[ClassificationCandidate]
    ) -> list[ClassificationCandidate]:
        return candidates


def test_build_classify_use_case_uses_rerank_override_when_given(
    indexed_collection: Collection,
) -> None:
    override = _FakeRerankOverride()
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
        rerank_override=override,
    )
    assert use_case._rerank is override


def test_build_classify_use_case_ignores_rerank_mode_when_override_given(
    indexed_collection: Collection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Even PASSTHROUGH (the default) is superseded by an explicit override.
    monkeypatch.setattr(settings, "rerank_mode", RerankMode.PASSTHROUGH)
    override = _FakeRerankOverride()
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
        rerank_override=override,
    )
    assert use_case._rerank is override


def test_resolve_rerank_override_returns_none_without_api_key() -> None:
    assert _resolve_rerank_override(None) is None
    assert _resolve_rerank_override("") is None


def test_resolve_rerank_override_builds_adapter_from_request_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.dependencies as deps

    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash")

    received: dict[str, str | None] = {}

    def _fake_resolve(provider: str, api_key: str | None = None) -> object:
        received["provider"] = provider
        received["api_key"] = api_key
        return object()

    monkeypatch.setattr(deps, "resolve_llm_client", _fake_resolve)

    override = _resolve_rerank_override("visitor-key")
    assert isinstance(override, GenericLLMRerankAdapter)
    assert override._model == "gemini-2.5-flash"
    assert received == {"provider": "google", "api_key": "visitor-key"}


def test_resolve_rerank_override_raises_http_422_for_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "not-a-real-provider")
    with pytest.raises(HTTPException) as exc_info:
        _resolve_rerank_override("visitor-key")
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# LLM-Provider / LLM-Model headers (ADR-0016): optional refinements, only
# consulted when X-LLM-Api-Key is present. Sending them alone must never
# trigger a call on the server's own credentials.
# ---------------------------------------------------------------------------


def test_resolve_rerank_override_uses_header_provider_and_model_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.dependencies as deps

    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash")

    received: dict[str, str | None] = {}

    def _fake_resolve(provider: str, api_key: str | None = None) -> object:
        received["provider"] = provider
        received["api_key"] = api_key
        return object()

    monkeypatch.setattr(deps, "resolve_llm_client", _fake_resolve)

    override = _resolve_rerank_override(
        "visitor-key", llm_provider="google", llm_model="gemini-2.5-pro"
    )
    assert isinstance(override, GenericLLMRerankAdapter)
    assert override._model == "gemini-2.5-pro"
    assert received == {"provider": "google", "api_key": "visitor-key"}


def test_resolve_rerank_override_falls_back_to_settings_when_headers_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.dependencies as deps

    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash")
    monkeypatch.setattr(deps, "resolve_llm_client", lambda provider, api_key=None: object())

    override = _resolve_rerank_override("visitor-key", llm_provider=None, llm_model=None)
    assert isinstance(override, GenericLLMRerankAdapter)
    assert override._model == "gemini-2.5-flash"


def test_provider_and_model_headers_alone_never_trigger_server_credential_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.dependencies as deps

    def _never_called(provider: str, api_key: str | None = None) -> object:
        raise AssertionError("resolve_llm_client must not be called without X-LLM-Api-Key")

    monkeypatch.setattr(deps, "resolve_llm_client", _never_called)

    # LLM-Provider/LLM-Model sent, but no X-LLM-Api-Key: no override, no call.
    assert _resolve_rerank_override(None, llm_provider="google", llm_model="gemini-2.5-pro") is None


# ---------------------------------------------------------------------------
# Credential isolation and discard (ADR-0016): each request's key produces its
# own ephemeral adapter/client; nothing about it survives past that call.
# ---------------------------------------------------------------------------


def test_two_requests_with_different_keys_get_distinct_adapters_and_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.api.dependencies as deps

    seen_keys: list[str | None] = []

    def _fake_resolve(provider: str, api_key: str | None = None) -> object:
        seen_keys.append(api_key)
        return object()  # a distinct client instance per call

    monkeypatch.setattr(deps, "resolve_llm_client", _fake_resolve)

    override_a = _resolve_rerank_override("key-a")
    override_b = _resolve_rerank_override("key-b")

    assert isinstance(override_a, GenericLLMRerankAdapter)
    assert isinstance(override_b, GenericLLMRerankAdapter)
    assert override_a is not override_b
    assert override_a._client is not override_b._client
    assert seen_keys == ["key-a", "key-b"]


def test_per_request_key_never_touches_settings_gemini_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "maintainers-own-key")

    _resolve_rerank_override("visitor-key-1")
    _resolve_rerank_override("visitor-key-2")

    # The maintainer's own credential is untouched by either request's key —
    # confirms the per-request path never reads or writes settings at all.
    assert settings.gemini_api_key == "maintainers-own-key"


def test_per_request_key_is_not_retained_on_the_built_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Uses the real resolve_llm_client -> GeminiClient (no fake): the only
    # place the key lives is GeminiClient._api_key on that one instance.
    override = _resolve_rerank_override("visitor-key")
    assert isinstance(override, GenericLLMRerankAdapter)
    client = override._client
    assert client._api_key == "visitor-key"
    # Nothing module-level captured it: a second, keyless resolution doesn't
    # see it either.
    other_client_via_settings = resolve_llm_client(settings.llm_provider)
    assert other_client_via_settings._api_key is None
