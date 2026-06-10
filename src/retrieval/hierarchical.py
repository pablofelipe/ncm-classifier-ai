from typing import Any, cast

from chromadb import Collection

from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.retrieval.embedding import E5EmbeddingFunction


class ChromaRetrievalAdapter:
    """Retrieval adapter over a ChromaDB collection.

    The embedding function is injected (not imported and built here): the
    composition root owns the real model. Queries are embedded with the
    "query: " prefix and matched against the passage-prefixed index, so the
    asymmetric e5 contract holds end to end.
    """

    def __init__(
        self, collection: Collection, embedding_fn: E5EmbeddingFunction
    ) -> None:
        self._collection = collection
        self._embedding_fn = embedding_fn

    def retrieve_candidates(
        self, query: ProductQuery, k: int
    ) -> list[ClassificationCandidate]:
        parts = [query.product_name]
        if query.description:
            parts.append(query.description)
        query_text = " ".join(parts)

        query_embedding = self._embedding_fn.embed_query(query_text)
        results = self._collection.query(
            query_embeddings=cast(Any, [query_embedding]),
            n_results=k,
        )

        distances = results["distances"]
        metadatas = results["metadatas"]
        if distances is None or metadatas is None:
            return []

        candidates: list[ClassificationCandidate] = []
        for distance, meta in zip(distances[0], metadatas[0], strict=True):
            metadata: dict[str, str | float] = {
                key: str(value) for key, value in meta.items()
            }
            candidates.append(
                ClassificationCandidate(
                    ncm_code=str(meta["ncm_dotted"]),
                    description=str(meta["description"]),
                    score=1.0 - distance,
                    metadata=metadata,
                )
            )

        return sorted(candidates, key=lambda c: c.score, reverse=True)
