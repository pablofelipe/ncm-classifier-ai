from typing import Protocol

from src.core.domain.ncm import ClassificationCandidate, ProductQuery


class RetrievalPort(Protocol):
    def retrieve_candidates(
        self, query: ProductQuery, k: int
    ) -> list[ClassificationCandidate]: ...


class LLMRerankPort(Protocol):
    def rerank(
        self,
        query: ProductQuery,
        candidates: list[ClassificationCandidate],
    ) -> list[ClassificationCandidate]: ...
