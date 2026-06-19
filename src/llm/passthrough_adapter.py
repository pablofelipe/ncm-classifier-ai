from src.core.domain.ncm import ClassificationCandidate, ProductQuery


class PassthroughRerankAdapter:
    """No-op rerank: returns the candidates unchanged.

    This is the shipping rerank today — the Gemini rerank path is not yet
    implemented (see src/llm/gemini_client.py). Validates LLMRerankPort with no
    external dependency (no Gemini API call). Preserves the order and content of
    the candidates it receives.
    """

    def rerank(
        self, query: ProductQuery, candidates: list[ClassificationCandidate]
    ) -> list[ClassificationCandidate]:
        return candidates
