from typing import Protocol, runtime_checkable

from src.core.domain.ncm import ClassificationCandidate, ProductQuery


@runtime_checkable
class RetrievalPort(Protocol):
    def retrieve_candidates(
        self, query: ProductQuery, k: int
    ) -> list[ClassificationCandidate]: ...


@runtime_checkable
class LLMRerankPort(Protocol):
    def rerank(
        self,
        query: ProductQuery,
        candidates: list[ClassificationCandidate],
    ) -> list[ClassificationCandidate]: ...
