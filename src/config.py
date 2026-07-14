from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.domain.enrichment import EnrichStrategy
from src.retrieval.embedding import EmbedderModel


class RerankMode(StrEnum):
    """Rerank strategy (env: RERANK_MODE).

    - PASSTHROUGH: no reranking — the ADR-0011 production default.
    - CROSS_ENCODER: local cross-encoder (mmarco-mMiniLMv2-L12-H384-v1),
      zero recurring cost. Rejected in ADR-0012 (domain gap). Kept for
      reproducibility; opt-in via RERANK_MODE=cross_encoder.
    - GEMINI: LLM rerank via the provider/model configured in LLM_PROVIDER /
      LLM_MODEL (ADR-0013, generalized in ADR-0016). Requires GEMINI_API_KEY
      (or a per-request credential, see ADR-0016) and the 'llm' extra.
      Opt-in via RERANK_MODE=gemini.
    """

    PASSTHROUGH = "passthrough"
    CROSS_ENCODER = "cross_encoder"
    GEMINI = "gemini"


class RetrievalMode(StrEnum):
    """Retrieval composition (env: RETRIEVAL_MODE), ADR-0011.

    - DENSE: e5-small only — the ADR-0004 production baseline (default).
    - HYBRID: BM25 + e5 fused by RRF, wired at the composition root. Reads the
      same Chroma documents as the dense index, so no index rebuild is needed and
      the existing index<->config guard still suffices.
    """

    DENSE = "dense"
    HYBRID = "hybrid"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Optional: PASSTHROUGH is the production default and needs no key, so
    # Settings() must instantiate without GEMINI_API_KEY in the environment.
    # This is the maintainer's own credential (local dev / CI / server-side
    # default rerank) — never the per-request "bring your own key" path
    # (ADR-0016), which reads its key from a request header, not from here.
    gemini_api_key: str | None = None
    # Generic LLM provider/model config (env: LLM_PROVIDER / LLM_MODEL,
    # ADR-0016), replacing Gemini-specific naming. llm_provider is a plain
    # str, not a StrEnum like RerankMode/RetrievalMode/EmbedderModel: those
    # enums gate a fixed if/elif in dependencies.py, while LLM_PROVIDER is
    # meant to stay open — new providers are a dict entry in
    # llm_client.resolve_llm_client, not an edit here.
    llm_provider: str = "google"
    llm_model: str = "gemini-2.5-flash"
    chroma_path: str = "data/chroma"
    tipi_data_dir: str = "data/tipi"
    confidence_threshold: float = 0.7
    ncm_chapter: str = "22"
    # Corpus-enrichment synonyms (env: SYNONYMS_PATH), ADR-0010: a NCM -> terms
    # JSON of brands and colloquial names absent from the official nomenclature.
    # Appended to OFF documents only (see build_document_text). Absent file ->
    # no enrichment (graceful); rebuild the index to apply.
    synonyms_path: str = "data/synonyms/beverage_synonyms.json"
    # Document-enrichment strategy (env: ENRICH_STRATEGY). OFF keeps the
    # ADR-0004 baseline (63.3% top-3); FULL is the ADR-0005 experiment (net
    # regression, kept reproducible); SUBHEADING_ONLY is ADR-0006 Form B
    # (inject the 6-digit product level, never the broad heading). The index
    # must be rebuilt to match; the adapter enforces index<->strategy agreement.
    enrich_strategy: EnrichStrategy = EnrichStrategy.OFF
    # Embedding model (env: EMBEDDER). E5_SMALL is the ADR-0004/0007 production
    # baseline; BGE_M3 is the ADR-0008 experiment, opt-in only. The index must be
    # rebuilt to match; the adapter enforces index<->embedder agreement.
    embedder: EmbedderModel = EmbedderModel.E5_SMALL
    # Retrieval mode (env: RETRIEVAL_MODE), ADR-0011. DENSE (default) keeps the
    # production dense-only path unchanged; HYBRID fuses BM25 + e5 via RRF at the
    # composition root. No index rebuild — BM25 reads the stored Chroma documents.
    retrieval_mode: RetrievalMode = RetrievalMode.DENSE
    # Rerank strategy (env: RERANK_MODE). PASSTHROUGH (default) keeps the
    # production path unchanged. CROSS_ENCODER loads the local cross-encoder
    # (rejected ADR-0012, kept for reproducibility). GEMINI calls Gemini Flash
    # (ADR-0013, requires GEMINI_API_KEY).
    rerank_mode: RerankMode = RerankMode.PASSTHROUGH
    # Rate limit (env: RATE_LIMIT_PER_MINUTE), Etapa 7: max POST /classify
    # requests per client IP per 60s window (src/api/rate_limit.py). Health
    # checks and other GETs are never throttled by this.
    rate_limit_per_minute: int = 20


# NOTE: instantiates at import time. CI environments must provide
# GEMINI_API_KEY (placeholder OK for skeleton).
# See .github/workflows/eval.yml.
settings = Settings()
