from chromadb import Collection

from src.config import settings
from src.core.use_cases.classify_product import ClassifyProduct
from src.llm.passthrough_adapter import PassthroughRerankAdapter
from src.retrieval.chroma_client import get_collection
from src.retrieval.embedding import E5EmbeddingFunction
from src.retrieval.hierarchical import ChromaRetrievalAdapter


def build_classify_use_case(
    collection: Collection | None = None,
    embedding_fn: E5EmbeddingFunction | None = None,
) -> ClassifyProduct:
    """Composition root: wire semantic retrieval (ADR-0004) into the use case.

    No FastAPI. Consumed both by the HTTP dependency below and by
    eval/run_eval.py (measurement layer), which calls the use case directly.

    `collection` and `embedding_fn` are injectable for tests; the defaults
    construct the real persistent Chroma collection and the pinned e5-small
    embedder. Rerank stays Passthrough until the Gemini rerank ADR lands.

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
    return ClassifyProduct(
        ChromaRetrievalAdapter(
            col,
            embedding_fn or E5EmbeddingFunction(),
            expected_enrich=settings.enrich_documents,
        ),
        PassthroughRerankAdapter(),
        confidence_threshold=settings.confidence_threshold,
    )


def get_classify_use_case() -> ClassifyProduct:
    """FastAPI driving-adapter wrapper around build_classify_use_case."""
    return build_classify_use_case()
