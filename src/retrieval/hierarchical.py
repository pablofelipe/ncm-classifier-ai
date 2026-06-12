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
        self,
        collection: Collection,
        embedding_fn: E5EmbeddingFunction,
        *,
        expected_enrich: bool,
    ) -> None:
        # Guard against an index built under a different document-text strategy
        # than the configured one (ADR-0005). expected_enrich is injected by the
        # composition root, not read from settings here (the adapter stays free
        # of config imports). A legacy index missing the key fails loudly too.
        stored = (collection.metadata or {}).get("enrich_documents")
        if stored != expected_enrich:
            raise RuntimeError(
                f"Index at collection '{collection.name}' was built with "
                f"enrich_documents={stored!r}, but config says {expected_enrich!r}. "
                "Rebuild the index: make index"
            )
        self._collection = collection
        self._embedding_fn = embedding_fn

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
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
            metadata: dict[str, str | float] = {key: str(value) for key, value in meta.items()}
            candidates.append(
                ClassificationCandidate(
                    ncm_code=str(meta["ncm_dotted"]),
                    description=str(meta["description"]),
                    score=1.0 - distance,
                    metadata=metadata,
                )
            )

        return sorted(candidates, key=lambda c: c.score, reverse=True)
