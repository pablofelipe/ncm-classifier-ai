from typing import Protocol, runtime_checkable

from src.core.domain.ncm import ClassificationCandidate, ProductQuery


@runtime_checkable
class RetrievalPort(Protocol):
    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]: ...


@runtime_checkable
class LLMRerankPort(Protocol):
    def rerank(
        self,
        query: ProductQuery,
        candidates: list[ClassificationCandidate],
    ) -> list[ClassificationCandidate]: ...


class LLMClient(Protocol):
    """Provider-agnostic LLM generation contract (ADR-0016).

    Represents the capability "ask an LLM to generate text", not any specific
    vendor SDK shape. GenericLLMRerankAdapter depends on this Protocol;
    concrete implementations (GeminiClient today, others later) translate
    generate() into their own SDK's call shape.
    """

    def generate(
        self,
        *,
        model: str,
        system_instruction: str,
        prompt: str,
        response_format: str = "application/json",
    ) -> str: ...
