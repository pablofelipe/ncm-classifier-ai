from src.core.domain.ncm import (
    ClassificationCandidate,
    ProductQuery,
    candidate_metadata_from_entry,
)


class NaiveRetrievalAdapter:
    """WALKING SKELETON — não rankeia, retorna primeiros k entries.

    Substituir por ChromaRetrievalAdapter quando ADR-0003 (embedding
    model selection) for aceito. Existe para estabelecer baseline
    reprodutível e validar RetrievalPort com >= 2 implementações.

    Determinismo: para a mesma lista de entries (carregada de uma TIPI
    JSON específica), retrieve_candidates retorna sempre os mesmos k
    candidatos na mesma ordem — a ordem em que aparecem em "entries".
    Não há embedding, tokenização nem modelo: apenas leitura ordenada.
    Todos os candidatos recebem score=0.0 para sinalizar explicitamente
    que este adapter não produz ranking. Quando k excede o número de
    entries disponíveis, retorna todos os disponíveis sem erro.
    """

    def __init__(self, entries: list[dict[str, object]]) -> None:
        self._entries = entries

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
        return [
            ClassificationCandidate(
                ncm_code=str(entry["ncm"]),
                description=str(entry["description"]),
                score=0.0,
                metadata=candidate_metadata_from_entry(entry),
            )
            for entry in self._entries[:k]
        ]
