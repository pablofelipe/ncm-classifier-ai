from src.core.domain.ncm import ClassificationCandidate, ProductQuery


class PassthroughRerankAdapter:
    """WALKING SKELETON — não rankeia, retorna os candidatos inalterados.

    Substituir por GeminiRerankAdapter quando ADR-0003 (embedding model
    selection) for aceito. Existe para estabelecer baseline reprodutível
    e validar LLMRerankPort sem dependências externas (nenhuma chamada à
    API do Gemini). Preserva ordem e conteúdo dos candidatos recebidos.
    """

    def rerank(
        self, query: ProductQuery, candidates: list[ClassificationCandidate]
    ) -> list[ClassificationCandidate]:
        return candidates
