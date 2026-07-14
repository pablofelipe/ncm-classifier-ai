import json
from pathlib import Path

from chromadb import Collection

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
) -> ClassifyProduct:
    """Composition root: wire semantic retrieval into the use case.

    No FastAPI. Consumed both by the HTTP dependency below and by
    eval/run_eval.py (measurement layer), which calls the use case directly.

    `collection` and `embedding_fn` are injectable for tests; the defaults
    construct the real persistent Chroma collection and the configured embedder
    (settings.embedder, default e5-small — the ADR-0007 production baseline; bge-m3
    opt-in via EMBEDDER for the ADR-0008 probe). Rerank defaults to Passthrough;
    opt-in to LLM rerank via RERANK_MODE=gemini (ADR-0013/0016).

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

    return ClassifyProduct(
        retrieval,
        reranker,
        confidence_threshold=settings.confidence_threshold,
        verification=_build_verification_index(),
    )


def get_classify_use_case() -> ClassifyProduct:
    """FastAPI driving-adapter wrapper around build_classify_use_case."""
    return build_classify_use_case()
