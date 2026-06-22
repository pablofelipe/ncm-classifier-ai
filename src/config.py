from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.domain.enrichment import EnrichStrategy
from src.retrieval.embedding import EmbedderModel


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Optional: the Gemini rerank path is not yet implemented (see
    # src/llm/gemini_client.py). Until the LLM-rerank ADR lands, the system
    # ships with Passthrough rerank and needs no key, so Settings() must
    # instantiate without GEMINI_API_KEY in the environment.
    gemini_api_key: str | None = None
    gemini_flash_model: str = "gemini-2.0-flash"
    gemini_pro_model: str = "gemini-2.0-pro"
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


# NOTE: instantiates at import time. CI environments must provide
# GEMINI_API_KEY (placeholder OK for skeleton).
# See .github/workflows/eval.yml.
settings = Settings()
