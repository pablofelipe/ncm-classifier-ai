# api/routes.py is a driving adapter: it translates HTTP requests
# into domain calls and domain results into HTTP responses. It
# legitimately imports from core.domain (ProductQuery,
# ClassificationResult) to perform this translation. The reverse
# (core importing from api) is forbidden.
import time
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_classify_use_case
from src.api.rate_limit import enforce_rate_limit
from src.api.schemas import ClassifyRequest, ClassifyResponse, NCMCandidate
from src.core.domain.ncm import ProductQuery
from src.core.use_cases.classify_product import ClassifyProduct

router = APIRouter()


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    dependencies=[Depends(enforce_rate_limit)],
    summary="Classify a product into its NCM fiscal code",
    description=(
        "Returns the top-3 candidate NCM codes for a product, ranked by "
        "confidence. Works with no credential at all (Passthrough or hybrid "
        "retrieval — zero LLM cost). Send your own Gemini API key via the "
        "X-LLM-Api-Key header to route through the stronger LLM-rerank path "
        "instead — it's used only for that one request, never persisted, "
        "logged, or cached (ADR-0016). Rate-limited per IP; see the 429 "
        "response for limits."
    ),
)
async def classify(
    request: ClassifyRequest,
    use_case: Annotated[ClassifyProduct, Depends(get_classify_use_case)],
) -> ClassifyResponse:
    query = ProductQuery(product_name=request.product_name, description=request.description)

    start = time.perf_counter()
    result = use_case.execute(query)
    latency_ms = (time.perf_counter() - start) * 1000.0

    return ClassifyResponse(
        confidence_label=result.confidence_label,
        candidates=[
            NCMCandidate(ncm=str(c.ncm_code), description=c.description, score=c.score)
            for c in result.top_candidates
        ],
        latency_ms=latency_ms,
        escalation_reason=result.escalation_reason,
    )
