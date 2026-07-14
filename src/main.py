from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.hardening import PayloadSizeLimitMiddleware, SecurityHeadersMiddleware
from src.api.routes import router as classify_router
from src.api.system import router as system_router
from src.llm.gemini_client import LLMProviderError

app = FastAPI(
    title="NCM Classifier",
    version="0.1.0",
    description=(
        "RAG pipeline that classifies Brazilian products into 8-digit NCM "
        "(Nomenclatura Comum do Mercosul) fiscal codes, grounded on the "
        "official TIPI table. Start at GET / for orientation, or POST "
        "/classify directly — no credential required. Bring your own LLM "
        "credential via X-LLM-Api-Key to unlock the higher-accuracy Gemini "
        "rerank path (see the /classify docs below); this deployment holds "
        "no LLM credential of its own. Source and decision log: "
        "https://github.com/pablofelipe/ncm-classifier-ai"
    ),
)

# Etapa 7 hardening. Middleware order matters: Starlette runs them in
# reverse-add order for the request path, so PayloadSizeLimit (added last)
# is the outermost/first check — reject an oversized body before CORS or
# security-header logic does any work on it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    # BYOK headers (ADR-0016) must be explicitly allowed for a cross-origin
    # browser client to send X-LLM-Api-Key/LLM-Provider/LLM-Model at all.
    allow_headers=["Content-Type", "X-LLM-Api-Key", "LLM-Provider", "LLM-Model"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PayloadSizeLimitMiddleware)

app.include_router(classify_router)
app.include_router(system_router)


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(request: Request, exc: LLMProviderError) -> JSONResponse:
    """Etapa 7: a provider rejection/outage becomes a clean 4xx/502, never an
    unhandled 500 with a stack trace (ADR-0016 Consequences)."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
