"""Embedding model identity for the ChromaDB retrieval adapter (ADR-0004).

These constants pin the exact embedding model and its HuggingFace revision used
both to build the index and to embed queries. They live here, in the retrieval
adapter layer, rather than in ``config.py`` on purpose: the revision is an
invariant of the indexed artifact, not an environment-specific setting. If it
were overridable via an environment variable, a deployment could silently
desynchronize the index from the evaluated baseline.

Model:    intfloat/multilingual-e5-small (multilingual, retrieval-native, 384-dim)
Revision: pinned below; captured 2026-04-02 (HuggingFace ``lastModified``).

Re-confirm the pin with:

    python -c "from huggingface_hub import HfApi; \
        print(HfApi().model_info('intfloat/multilingual-e5-small').sha)"

See ADR-0004 for the embedder selection rationale and the eval baseline.
"""

from enum import StrEnum
from typing import Any, Protocol, cast

EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
EMBEDDING_DIM = 384

# e5 models require asymmetric prefixes: documents are encoded as "passage: ",
# queries as "query: ". Omitting or mixing them silently degrades retrieval.
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


class _Encoder(Protocol):
    """Structural type for the underlying sentence encoder (SentenceTransformer
    in production, a spy in tests). Only the slice we use is declared."""

    def encode(self, sentences: list[str], normalize_embeddings: bool = ...) -> Any: ...


class EmbeddingFunction(Protocol):
    """Structural contract shared by the retrieval embedders.

    Two concrete implementations exist with materially different contracts:
    :class:`E5EmbeddingFunction` is *asymmetric* (it prefixes documents and
    queries differently), while :class:`BGEEmbeddingFunction` is *symmetric*
    (no prefix at all). That difference is semantic, not configuration, so they
    are separate subclasses rather than one parametrized one — but the model
    loading and encode plumbing they share lives in
    :class:`_SentenceTransformerEmbedder`. The ChromaDB adapter and the indexer
    depend on this Protocol, so either embedder can be injected at the
    composition root without the consumers knowing which model is live.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class _SentenceTransformerEmbedder:
    """Shared base for SentenceTransformer-backed embedders.

    Owns only what is identical across embedders: the revision-pinned, lazily
    built encoder and the normalize → to-list encode step. Subclasses define the
    prefix contract by overriding ``embed_documents`` / ``embed_query`` — that is
    the *only* difference between e5 (asymmetric) and bge (symmetric).

    The underlying encoder is injectable so the prefix logic can be unit-tested
    without loading the model. When omitted, the pinned SentenceTransformer is
    built lazily on first use (revision-locked for reproducibility).
    """

    def __init__(
        self,
        encoder: _Encoder | None = None,
        *,
        model_name: str,
        revision: str | None,
    ) -> None:
        if not revision:
            raise ValueError("embedding model revision must be pinned; got an empty value")
        self._encoder = encoder
        self._model_name = model_name
        self._revision = revision

    def _get_encoder(self) -> _Encoder:
        encoder = self._encoder
        if encoder is None:
            from sentence_transformers import SentenceTransformer

            # SentenceTransformer is structurally an _Encoder but its wider
            # encode() signature doesn't match the Protocol nominally.
            encoder = cast(_Encoder, SentenceTransformer(self._model_name, revision=self._revision))
            self._encoder = encoder
        return encoder

    def _encode(self, sentences: list[str]) -> list[list[float]]:
        raw = self._get_encoder().encode(sentences, normalize_embeddings=True)
        tolist = getattr(raw, "tolist", None)
        matrix = tolist() if callable(tolist) else raw
        return [list(row) for row in matrix]


class E5EmbeddingFunction(_SentenceTransformerEmbedder):
    """Asymmetric e5 embedder for the ChromaDB retrieval adapter (ADR-0004).

    e5 needs a different prefix for documents (``passage: ``) and queries
    (``query: ``); a symmetric ``__call__`` would prefix queries as passages — a
    silent quality bug. Callers must pick ``embed_documents`` or ``embed_query``
    explicitly. This is the shipping embedder.
    """

    def __init__(
        self,
        encoder: _Encoder | None = None,
        *,
        model_name: str = EMBEDDING_MODEL_NAME,
        revision: str | None = EMBEDDING_MODEL_REVISION,
    ) -> None:
        super().__init__(encoder, model_name=model_name, revision=revision)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed TIPI document texts (raw, without prefix — the prefix is added
        here, not by the caller)."""
        return self._encode([PASSAGE_PREFIX + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Embed a single product query."""
        return self._encode([QUERY_PREFIX + text])[0]


# bge-m3 (ADR-0008). Pinned to the captured revision below (HuggingFace ``sha``,
# 2024-07-03 ``lastModified``). Re-confirm with:
#
#     python -c "from huggingface_hub import HfApi; \
#         print(HfApi().model_info('BAAI/bge-m3').sha)"
BGE_EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
BGE_EMBEDDING_MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
BGE_EMBEDDING_DIM = 1024


class BGEEmbeddingFunction(_SentenceTransformerEmbedder):
    """Symmetric bge-m3 embedder for the ChromaDB retrieval adapter (ADR-0008).

    Unlike e5, bge-m3 takes NO prefix on either side. The model card states the
    model "no longer requires adding instructions to the queries", and its
    sentence-transformers config declares no prompt; passages carry no
    instruction either. Documents and queries are therefore encoded from the raw
    text, identically — there is no document-vs-query distinction beyond the
    list-vs-single shape. Carrying over e5's "query: "/"passage: " prefixes here
    would be a silent quality bug, which is why this is a separate subclass.

    Dense-only: SentenceTransformer loads the model's Transformer -> CLS pooling
    -> Normalize pipeline (a single 1024-dim normalized vector). The sparse and
    ColBERT heads shipped in the repo are not part of that pipeline and are never
    activated. Opt-in (ADR-0008 rejected it for production); not in the shipping
    path.
    """

    def __init__(
        self,
        encoder: _Encoder | None = None,
        *,
        model_name: str = BGE_EMBEDDING_MODEL_NAME,
        revision: str | None = BGE_EMBEDDING_MODEL_REVISION,
    ) -> None:
        super().__init__(encoder, model_name=model_name, revision=revision)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed TIPI document texts from the raw text — no prefix (bge is symmetric)."""
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single product query from the raw text — no prefix (bge is symmetric)."""
        return self._encode([text])[0]


class EmbedderModel(StrEnum):
    """Embedding model selector for the TIPI index (ADR-0008).

    Pure infrastructure (unlike EnrichStrategy, which composes document text and
    is borderline-domain): which model produces the vectors is an adapter choice.
    The value is stored as Chroma collection metadata and read from the EMBEDDER
    env var, so index and config can be checked for agreement — a mismatch means
    one model built the index and another reads it (incompatible space), the
    silent-degradation failure the dimension check alone cannot catch for two
    same-dimension models (see ChromaRetrievalAdapter).

    - E5_SMALL: multilingual-e5-small, the ADR-0004 baseline (production default).
    - BGE_M3: BAAI/bge-m3 dense, the ADR-0008 experiment.
    """

    E5_SMALL = "e5_small"
    BGE_M3 = "bge_m3"


def make_embedding_function(model: EmbedderModel) -> EmbeddingFunction:
    """Map the configured embedder enum to a concrete embedding function.

    The single selection point: the composition root and the indexer call this
    with ``settings.embedder`` instead of constructing a class directly.
    """
    if model is EmbedderModel.E5_SMALL:
        return E5EmbeddingFunction()
    if model is EmbedderModel.BGE_M3:
        return BGEEmbeddingFunction()
    raise ValueError(f"unknown embedder: {model!r}")
