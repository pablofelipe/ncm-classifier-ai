# Operational endpoints (Etapa 4, Release Polish): GET /, GET /version,
# GET /info. Kept apart from routes.py on purpose — routes.py is the
# classification domain's HTTP surface; this module is diagnostics and
# orientation, with no business logic.
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.api.dependencies import get_index_info
from src.api.schemas import IndexInfo, InfoResponse, LLMInfo, RootResponse
from src.config import settings

router = APIRouter()


@router.get(
    "/",
    response_model=RootResponse,
    summary="API landing page",
    description=(
        "Entry point for first-time visitors: what this API does, where the "
        "interactive docs live, and the other endpoints available. For the "
        "full deployment/retrieval diagnostic snapshot, see GET /info."
    ),
)
async def root(request: Request) -> RootResponse:
    return RootResponse(
        name="NCM Classifier",
        description=(
            "RAG pipeline that classifies Brazilian products into 8-digit NCM "
            "fiscal codes, grounded on the official TIPI table."
        ),
        version=request.app.version,
        deployment_profile=(
            "Default Public Deployment Profile — see GET /info for retrieval "
            "mode, rerank mode, and index details."
        ),
        docs="/docs",
        endpoints={
            "classify": "POST /classify",
            "health": "GET /health",
            "version": "GET /version",
            "info": "GET /info",
        },
    )


@router.get(
    "/health",
    summary="Liveness check",
    description=(
        "No-op health probe — no auth, no LLM call, no dependency on the "
        "retrieval index. Used by the deployment platform's health checks "
        "(see fly.toml)."
    ),
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/version",
    summary="Application version",
    description="Just the version string — see GET /info for a full diagnostic snapshot.",
)
async def version(request: Request) -> dict[str, str]:
    return {"version": request.app.version}


@router.get(
    "/info",
    response_model=InfoResponse,
    summary="Deployment diagnostic snapshot",
    description=(
        "Which index is loaded, which retrieval/rerank modes are active, and "
        "whether Bring Your Own LLM Credentials (ADR-0016) is supported. "
        "Never includes credentials — see IndexInfo/LLMInfo field docs."
    ),
)
async def info(
    request: Request,
    index_info: Annotated[IndexInfo, Depends(get_index_info)],
) -> InfoResponse:
    return InfoResponse(
        version=request.app.version,
        index=index_info,
        retrieval_mode=settings.retrieval_mode.value,
        rerank_mode=settings.rerank_mode.value,
        llm=LLMInfo(
            default_provider=settings.llm_provider,
            default_model=settings.llm_model,
            byok_supported=True,
            byok_headers=["X-LLM-Api-Key", "LLM-Provider", "LLM-Model"],
        ),
    )
