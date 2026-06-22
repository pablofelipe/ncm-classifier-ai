from chromadb import Collection

from src.config import RetrievalMode, settings
from src.core.ports import RetrievalPort
from src.core.use_cases.classify_product import ClassifyProduct
from src.llm.passthrough_adapter import PassthroughRerankAdapter
from src.retrieval.bm25_adapter import BM25RetrievalAdapter
from src.retrieval.chroma_client import get_collection
from src.retrieval.embedding import EmbeddingFunction, make_embedding_function
from src.retrieval.hierarchical import ChromaRetrievalAdapter
from src.retrieval.hybrid import HybridRetrievalAdapter


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
    opt-in via EMBEDDER for the ADR-0008 probe). Rerank stays Passthrough until
    the Gemini rerank ADR lands.

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

    return ClassifyProduct(
        retrieval,
        PassthroughRerankAdapter(),
        confidence_threshold=settings.confidence_threshold,
    )


def get_classify_use_case() -> ClassifyProduct:
    """FastAPI driving-adapter wrapper around build_classify_use_case."""
    return build_classify_use_case()
