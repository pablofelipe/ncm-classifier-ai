# api/routes.py is a driving adapter: it translates HTTP requests
# into domain calls and domain results into HTTP responses. It
# legitimately imports from core.domain (ProductQuery,
# ClassificationResult) to perform this translation. The reverse
# (core importing from api) is forbidden.
import time
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_classify_use_case
from src.api.schemas import ClassifyRequest, ClassifyResponse, NCMCandidate
from src.core.domain.ncm import ProductQuery
from src.core.use_cases.classify_product import ClassifyProduct

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
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
            NCMCandidate(ncm=c.ncm_code, description=c.description, score=c.score)
            for c in result.top_candidates
        ],
        latency_ms=latency_ms,
    )
