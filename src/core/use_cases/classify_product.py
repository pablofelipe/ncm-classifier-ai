from src.core.domain.ncm import ClassificationResult, ConfidenceLabel, ProductQuery
from src.core.ports import LLMRerankPort, RetrievalPort
from src.core.verification.deterministic import TIPIIndex

_RETRIEVAL_K = 10
_TOP_N = 3


class ClassifyProduct:
    """Use case: classify a product into NCM candidates.

    WALKING SKELETON — orchestrates retrieval + rerank + confidence
    gating. Substitutes for a smarter pipeline when ADR-0003 lands.
    """

    def __init__(
        self,
        retrieval: RetrievalPort,
        rerank: LLMRerankPort,
        confidence_threshold: float = 0.5,
        verification: TIPIIndex | None = None,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError(
                f"confidence_threshold must be within [0.0, 1.0], got {confidence_threshold}"
            )
        self._retrieval = retrieval
        self._rerank = rerank
        # T will be recalibrated in ADR-0004 after the first eval run against
        # real retrieval — the 0.5 default is a placeholder for the skeleton,
        # where every score is 0.0 and the label is always "needs_review".
        self._confidence_threshold = confidence_threshold
        # ADR-0014: optional verification gate. None preserves the pre-ADR-0014
        # score-only gating (eval scripts and callers that don't inject a
        # TIPIIndex are unaffected).
        self._verification = verification

    def execute(self, query: ProductQuery) -> ClassificationResult:
        candidates = self._retrieval.retrieve_candidates(query, k=_RETRIEVAL_K)
        reranked = self._rerank.rerank(query, candidates)
        top = reranked[:_TOP_N]

        escalation_reason: str | None = None
        verification_failed = False
        if self._verification is not None:
            dotless_code = top[0].ncm_code.replace(".", "")
            verification_result = self._verification.verify(dotless_code)
            if not verification_result.passed:
                verification_failed = True
                escalation_reason = verification_result.status.value

        label: ConfidenceLabel = (
            "needs_review"
            if verification_failed or top[0].score < self._confidence_threshold
            else "high"
        )
        return ClassificationResult(
            top_candidates=top, confidence_label=label, escalation_reason=escalation_reason
        )
