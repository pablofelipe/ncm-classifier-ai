from src.core.domain.ncm import (
    ClassificationCandidate,
    NCMCode,
    ProductQuery,
    candidate_metadata_from_entry,
)


class NaiveRetrievalAdapter:
    """Walking-skeleton retrieval: no ranking, returns the first k entries.

    Superseded in production by ChromaRetrievalAdapter (ADR-0004, shipping);
    kept as the baseline second implementation of RetrievalPort and used by
    tests. Establishes a reproducible baseline and validates the port with >= 2
    implementations.

    Determinism: for the same entries list (loaded from a specific TIPI JSON),
    retrieve_candidates always returns the same k candidates in the same order
    — the order they appear in ``entries``. No embedding, tokenization or model:
    just an ordered read. Every candidate gets score=0.0 to signal explicitly
    that this adapter produces no ranking. When k exceeds the number of
    available entries, it returns all of them without error.
    """

    def __init__(self, entries: list[dict[str, object]]) -> None:
        self._entries = entries

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
        return [
            ClassificationCandidate(
                ncm_code=NCMCode(str(entry["ncm"])),
                description=str(entry["description"]),
                score=0.0,
                metadata=candidate_metadata_from_entry(entry),
            )
            for entry in self._entries[:k]
        ]
