"""Cross-encoder rerank adapter (ADR-0012).

Model:    cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
          Multilingual MiniLM, trained on mMARCO (includes PT), 384-dim hidden.
Revision: pinned below; captured 2026-06-28 (HuggingFace ``lastModified``).

Re-confirm the pin with:

    python -c "from huggingface_hub import HfApi; \\
        print(HfApi().model_info('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1').sha)"

The returned score is a raw logit (not a probability). The confidence gate
must be recalibrated against this scale — same caveat as the RRF score from
ADR-0011.
"""

from typing import Any, Protocol

from src.core.domain.ncm import ClassificationCandidate, ProductQuery

CROSS_ENCODER_MODEL_NAME = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
CROSS_ENCODER_MODEL_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"


class _CrossEncoderProtocol(Protocol):
    def predict(self, pairs: list[tuple[str, str]]) -> Any: ...


class CrossEncoderRerankAdapter:
    """Rerank candidates with a local cross-encoder (ADR-0012).

    Satisfies ``LLMRerankPort``. The underlying model is injectable so the
    scoring logic can be unit-tested without downloading the ~120 MB weights.
    When omitted, the pinned ``CrossEncoder`` is built lazily on first use.
    """

    def __init__(self, encoder: _CrossEncoderProtocol | None = None) -> None:
        self._encoder = encoder

    def _get_encoder(self) -> _CrossEncoderProtocol:
        if self._encoder is None:
            from sentence_transformers import CrossEncoder

            self._encoder = CrossEncoder(
                CROSS_ENCODER_MODEL_NAME,
                revision=CROSS_ENCODER_MODEL_REVISION,
            )
        return self._encoder

    def rerank(
        self,
        query: ProductQuery,
        candidates: list[ClassificationCandidate],
    ) -> list[ClassificationCandidate]:
        if not candidates:
            return []

        query_text = query.product_name
        if query.description:
            query_text += " " + query.description

        encoder = self._get_encoder()
        pairs = [(query_text, c.description) for c in candidates]
        raw_scores = encoder.predict(pairs)

        scored = sorted(
            zip(candidates, raw_scores, strict=False),
            key=lambda x: float(x[1]),
            reverse=True,
        )
        return [
            ClassificationCandidate(
                ncm_code=c.ncm_code,
                description=c.description,
                score=float(s),
                metadata=c.metadata,
            )
            for c, s in scored
        ]
