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


class E5EmbeddingFunction:
    """Asymmetric e5 embedder for the ChromaDB retrieval adapter.

    Deliberately NOT a Chroma single-callable ``EmbeddingFunction``: e5 needs a
    different prefix for documents (``passage: ``) and queries (``query: ``),
    and a symmetric ``__call__`` would prefix queries as passages — a silent
    quality bug. Callers must pick ``embed_documents`` or ``embed_query``
    explicitly.

    The underlying encoder is injectable so prefix logic can be unit-tested
    without loading the model. When omitted, the pinned SentenceTransformer is
    built lazily on first use (revision-locked for reproducibility).
    """

    def __init__(
        self,
        encoder: _Encoder | None = None,
        *,
        model_name: str = EMBEDDING_MODEL_NAME,
        revision: str | None = EMBEDDING_MODEL_REVISION,
        dim: int = EMBEDDING_DIM,
    ) -> None:
        if not revision:
            raise ValueError("embedding model revision must be pinned; got an empty value")
        self._encoder = encoder
        self._model_name = model_name
        self._revision = revision
        self._dim = dim

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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed TIPI document texts (raw, without prefix — the prefix is added
        here, not by the caller)."""
        return self._encode([PASSAGE_PREFIX + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        """Embed a single product query."""
        return self._encode([QUERY_PREFIX + text])[0]
