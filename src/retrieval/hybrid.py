from collections import defaultdict

from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.core.ports import RetrievalPort


class HybridRetrievalAdapter:
    """Fuse two ``RetrievalPort`` rankings with Reciprocal Rank Fusion (ADR-0011).

    Composes a dense and a lexical retriever — each itself a ``RetrievalPort`` —
    and is one too, so the use case is unchanged. RRF score per NCM is
    ``Σ 1/(k_rrf + rank + 1)`` over the retrievers that returned it (rank 0-based);
    candidates are fused by ``ncm_code``. ``k_rrf=60`` is the standard constant,
    no critical hyperparameter. Each retriever is queried for a generous ``pool``
    (≥ the corpus) so the two rankings overlap before fusion.

    The returned candidate's ``score`` is the RRF score — no longer ``1 - cosine``.
    The confidence gate must be recalibrated against this scale before it is read
    as a probability (rerank is still Passthrough, threshold a placeholder).
    """

    def __init__(
        self,
        dense: RetrievalPort,
        lexical: RetrievalPort,
        *,
        k_rrf: int = 60,
        pool: int = 64,
    ) -> None:
        self._dense = dense
        self._lexical = lexical
        self._k_rrf = k_rrf
        self._pool = pool

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
        rrf: dict[str, float] = defaultdict(float)
        first_seen: dict[str, ClassificationCandidate] = {}
        for retriever in (self._dense, self._lexical):
            for rank, candidate in enumerate(retriever.retrieve_candidates(query, self._pool)):
                rrf[candidate.ncm_code] += 1.0 / (self._k_rrf + rank + 1)
                first_seen.setdefault(candidate.ncm_code, candidate)

        ordered = sorted(first_seen.values(), key=lambda c: rrf[c.ncm_code], reverse=True)
        return [
            ClassificationCandidate(
                ncm_code=c.ncm_code,
                description=c.description,
                score=rrf[c.ncm_code],
                metadata=c.metadata,
            )
            for c in ordered[:k]
        ]
