from typing import Any, cast

from chromadb import Collection

from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.ncm import ClassificationCandidate, NCMCode, ProductQuery
from src.retrieval.embedding import EmbedderModel, EmbeddingFunction


class ChromaRetrievalAdapter:
    """Retrieval adapter over a ChromaDB collection.

    The embedding function is injected (not imported and built here): the
    composition root owns the real model. The adapter is embedder-agnostic — it
    calls ``embed_query`` and lets the embedder apply whatever prefix contract
    it owns (bge-m3 none, ADR-0008; e5 the asymmetric "query: "). The index must
    be built with the same embedder, which the rebuild guarantees.
    """

    def __init__(
        self,
        collection: Collection,
        embedding_fn: EmbeddingFunction,
        *,
        expected_strategy: EnrichStrategy,
        expected_embedder: EmbedderModel,
    ) -> None:
        # Guard against an index whose provenance disagrees with config. Both the
        # embedder (ADR-0008) and the document-text strategy (ADR-0005/0006) are
        # injected by the composition root, not read from settings here (the
        # adapter stays free of config imports). The two are checked separately,
        # embedder first: a different embedder means an incompatible vector space
        # (the index is unusable), a more fundamental incompatibility than a
        # strategy difference (same space, different document content). Each
        # message names the field that diverged. A legacy index — missing either
        # key, or carrying the old bool "enrich_documents" key — fails loudly.
        meta = collection.metadata or {}
        stored_embedder = meta.get("embedder")
        if stored_embedder != expected_embedder.value:
            raise RuntimeError(
                f"Index at collection '{collection.name}' was built with "
                f"embedder={stored_embedder!r}, but config says "
                f"{expected_embedder.value!r}. Rebuild the index: make index"
            )
        stored_strategy = meta.get("enrich_strategy")
        if stored_strategy != expected_strategy.value:
            raise RuntimeError(
                f"Index at collection '{collection.name}' was built with "
                f"enrich_strategy={stored_strategy!r}, but config says "
                f"{expected_strategy.value!r}. Rebuild the index: make index"
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
                    ncm_code=NCMCode(str(meta["ncm_dotted"])),
                    description=str(meta["description"]),
                    score=1.0 - distance,
                    metadata=metadata,
                )
            )

        return sorted(candidates, key=lambda c: c.score, reverse=True)
