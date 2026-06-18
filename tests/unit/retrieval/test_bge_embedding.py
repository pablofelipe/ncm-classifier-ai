"""Unit tests for the bge-m3 embedding function — symmetry and pin logic (ADR-0008).

bge-m3 is symmetric: it takes NO prefix on either side (model card verbatim —
"the BGE-M3 model no longer requires adding instructions to the queries", and the
sentence-transformers config declares no prompt). These spy-based tests assert
the encoder receives the RAW text, identically for documents and queries — the
guard against carrying over e5's asymmetric "query: "/"passage: " prefixes.

The real-model dimension (1024) and the same-text-same-vector symmetry guard
live in tests/integration/retrieval/test_bge_embedding.py.
"""

import pytest

from src.retrieval.embedding import BGE_EMBEDDING_DIM, BGEEmbeddingFunction


class SpyEncoder:
    """Records the exact strings handed to encode; returns dummy vectors.

    The only reliable guard against "prefix silently applied" (or, here, the
    opposite mistake of inheriting e5's prefixes): assert on what the model
    would actually receive.
    """

    def __init__(self, dim: int = BGE_EMBEDDING_DIM) -> None:
        self.seen: list[str] = []
        self._dim = dim

    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        self.seen.extend(sentences)
        return [[0.0] * self._dim for _ in sentences]


def test_documents_embedded_without_prefix() -> None:
    spy = SpyEncoder()
    ef = BGEEmbeddingFunction(encoder=spy)

    ef.embed_documents(["Cervejas de malte"])

    assert spy.seen == ["Cervejas de malte"]


def test_queries_embedded_without_prefix() -> None:
    spy = SpyEncoder()
    ef = BGEEmbeddingFunction(encoder=spy)

    ef.embed_query("Cervejas de malte")

    assert spy.seen == ["Cervejas de malte"]


def test_query_and_document_receive_identical_text() -> None:
    # The semantic guard: bge-m3 is symmetric. The same product text must reach
    # the encoder byte-for-byte whether embedded as a document or a query —
    # proving no asymmetric prefix leaked in from the e5 contract.
    text = "Cervejas de malte"
    doc_spy = SpyEncoder()
    query_spy = SpyEncoder()

    BGEEmbeddingFunction(encoder=doc_spy).embed_documents([text])
    BGEEmbeddingFunction(encoder=query_spy).embed_query(text)

    assert doc_spy.seen == query_spy.seen == [text]


@pytest.mark.parametrize("bad_revision", [None, ""])
def test_revision_is_pinned(bad_revision: str | None) -> None:
    with pytest.raises(ValueError):
        BGEEmbeddingFunction(revision=bad_revision)
