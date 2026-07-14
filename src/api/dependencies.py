import json
from pathlib import Path

from chromadb import Collection
from fastapi import Header, HTTPException

from src.api.schemas import IndexInfo
from src.config import RerankMode, RetrievalMode, settings
from src.core.ports import LLMRerankPort, RetrievalPort
from src.core.use_cases.classify_product import ClassifyProduct
from src.core.verification.deterministic import TIPIIndex
from src.llm.cross_encoder_adapter import CrossEncoderRerankAdapter
from src.llm.generic_llm_rerank_adapter import GenericLLMRerankAdapter
from src.llm.llm_client import resolve_llm_client
from src.llm.passthrough_adapter import PassthroughRerankAdapter
from src.retrieval.bm25_adapter import BM25RetrievalAdapter
from src.retrieval.chroma_client import _find_latest_tipi_json, get_collection
from src.retrieval.embedding import EmbeddingFunction, make_embedding_function
from src.retrieval.hierarchical import ChromaRetrievalAdapter
from src.retrieval.hybrid import HybridRetrievalAdapter


def _build_verification_index() -> TIPIIndex:
    """Build the ADR-0014 verification index from the same TIPI JSON used to
    populate the Chroma collection (settings.tipi_data_dir / settings.ncm_chapter).
    """
    data_dir = Path(settings.tipi_data_dir)
    json_path = _find_latest_tipi_json(data_dir, settings.ncm_chapter)
    entries = json.loads(json_path.read_text(encoding="utf-8"))["entries"]
    codes = {
        entry["ncm"].replace(".", ""): {
            "chapter": entry["chapter"],
            "heading": entry["heading"],
            "description": entry["description"],
        }
        for entry in entries
    }
    return TIPIIndex(codes)


def build_classify_use_case(
    collection: Collection | None = None,
    embedding_fn: EmbeddingFunction | None = None,
    *,
    rerank_override: LLMRerankPort | None = None,
) -> ClassifyProduct:
    """Composition root: wire semantic retrieval into the use case.

    No FastAPI. Consumed both by the HTTP dependency below and by
    eval/run_eval.py (measurement layer), which calls the use case directly.

    `collection` and `embedding_fn` are injectable for tests; the defaults
    construct the real persistent Chroma collection and the configured embedder
    (settings.embedder, default e5-small — the ADR-0007 production baseline; bge-m3
    opt-in via EMBEDDER for the ADR-0008 probe). Rerank defaults to Passthrough;
    opt-in to LLM rerank via RERANK_MODE=gemini (ADR-0013/0016).

    `rerank_override` (ADR-0016), when given, supersedes settings.rerank_mode
    entirely — this is how a per-request "bring your own LLM credentials"
    header (see `get_classify_use_case`) reaches the pipeline without the use
    case or any port ever knowing about credentials or vendors.

    Raises RuntimeError when the index has not been built — an explicit
    failure at startup beats a silent fallback that would mask a
    misconfigured deployment.
    """
    col = collection if collection is not None else get_collection()
    if col.count() == 0:
        raise RuntimeError(
            f"Chroma collection '{col.name}' at '{settings.chroma_path}' is empty: "
            "the semantic index has not been built. Run: make index"
        )
    dense = ChromaRetrievalAdapter(
        col,
        embedding_fn or make_embedding_function(settings.embedder),
        expected_strategy=settings.enrich_strategy,
        expected_embedder=settings.embedder,
    )
    # ADR-0011: HYBRID fuses BM25 (lexical, built from the same Chroma documents)
    # with the dense retriever via RRF. DENSE keeps the production path untouched.
    retrieval: RetrievalPort = dense
    if settings.retrieval_mode is RetrievalMode.HYBRID:
        retrieval = HybridRetrievalAdapter(dense, BM25RetrievalAdapter(col))

    # Rerank adapter: PASSTHROUGH (default) keeps the production path unchanged.
    # CROSS_ENCODER loads the local cross-encoder (rejected ADR-0012, reproducibility).
    # GEMINI resolves the configured LLM_PROVIDER/LLM_MODEL via GenericLLMRerankAdapter
    # (ADR-0016; provider-agnostic, supersedes the retired Gemini-specific adapter).
    reranker: LLMRerankPort = PassthroughRerankAdapter()
    if settings.rerank_mode is RerankMode.CROSS_ENCODER:
        reranker = CrossEncoderRerankAdapter()
    elif settings.rerank_mode is RerankMode.GEMINI:
        reranker = GenericLLMRerankAdapter(
            resolve_llm_client(settings.llm_provider), model=settings.llm_model
        )
    if rerank_override is not None:
        reranker = rerank_override

    return ClassifyProduct(
        retrieval,
        reranker,
        confidence_threshold=settings.confidence_threshold,
        verification=_build_verification_index(),
    )


def _resolve_rerank_override(
    x_llm_api_key: str | None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> LLMRerankPort | None:
    """Build the ADR-0016 per-request rerank override from raw header values.

    Returns None when no key was sent — the pipeline then falls back to
    settings.rerank_mode unchanged (see build_classify_use_case). The key
    lives only in this call's stack frame: it flows straight into a freshly
    constructed GenericLLMRerankAdapter/GeminiClient and is never assigned to
    settings, a module global, or a cache.

    llm_provider/llm_model are optional refinements, defaulting to
    settings.llm_provider/settings.llm_model when absent — and are only ever
    consulted inside this "key present" branch. Sending them without a key
    never triggers a call on the server's own credentials.
    """
    if not x_llm_api_key:
        return None
    provider = llm_provider or settings.llm_provider
    model = llm_model or settings.llm_model
    try:
        client = resolve_llm_client(provider, api_key=x_llm_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GenericLLMRerankAdapter(client, model=model)


def get_classify_use_case(
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-Api-Key"),
    llm_provider: str | None = Header(default=None, alias="LLM-Provider"),
    llm_model: str | None = Header(default=None, alias="LLM-Model"),
) -> ClassifyProduct:
    """FastAPI driving-adapter wrapper around build_classify_use_case.

    ADR-0016: reads the optional X-LLM-Api-Key header — a visitor's own LLM
    credential, used only for this one request's rerank call — plus the
    optional LLM-Provider/LLM-Model headers, which refine which provider/model
    that credential is used against (defaulting to settings when omitted).
    The public deployment ships with no server-side LLM key, so this is the
    only way a request gets LLM rerank there; without X-LLM-Api-Key, the
    pipeline runs whatever settings.rerank_mode configures server-side
    (Passthrough in production).
    """
    return build_classify_use_case(
        rerank_override=_resolve_rerank_override(x_llm_api_key, llm_provider, llm_model)
    )


def build_index_info(collection: Collection | None = None) -> IndexInfo:
    """Composition-root logic for GET /info (Etapa 4, ADR-0015).

    Read-only diagnostic snapshot of the loaded Chroma collection: name, entry
    count, and the embedder/enrich_strategy metadata already recorded at index
    time (see chroma_client.index_entries), plus the TIPI source filename
    baked into the image. Never touches a credential — there is nothing here
    settings.gemini_api_key-adjacent to read.

    `collection` is injectable for tests (mirrors build_classify_use_case);
    the default constructs the real persistent Chroma collection. Not used
    directly as a FastAPI dependency: a `Collection | None` parameter isn't a
    type FastAPI can build a request field for (see get_index_info below).
    """
    col = collection if collection is not None else get_collection()
    data_dir = Path(settings.tipi_data_dir)
    source = _find_latest_tipi_json(data_dir, settings.ncm_chapter).name
    metadata = col.metadata or {}
    return IndexInfo(
        collection=col.name,
        source=source,
        entries=col.count(),
        embedder=str(metadata.get("embedder", "unknown")),
        enrich_strategy=str(metadata.get("enrich_strategy", "unknown")),
    )


def get_index_info() -> IndexInfo:
    """FastAPI driving-adapter wrapper around build_index_info (no parameters
    FastAPI would need to build a request field for — mirrors get_classify_use_case)."""
    return build_index_info()
