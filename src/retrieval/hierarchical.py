from chromadb import Collection

from src.core.domain.ncm import ClassificationCandidate, ProductQuery


class ChromaRetrievalAdapter:
    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def retrieve_candidates(
        self, query: ProductQuery, k: int
    ) -> list[ClassificationCandidate]:
        parts = [query.product_name]
        if query.description:
            parts.append(query.description)
        query_text = " ".join(parts)

        results = self._collection.query(
            query_texts=[query_text],
            n_results=k,
        )

        candidates: list[ClassificationCandidate] = []
        for ncm_id, distance, meta in zip(
            results["ids"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            candidates.append(
                ClassificationCandidate(
                    ncm_code=meta["ncm_dotted"],
                    description=meta["description"],
                    score=1.0 - distance,
                    metadata=meta,
                )
            )

        return sorted(candidates, key=lambda c: c.score, reverse=True)
