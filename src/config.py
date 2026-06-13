from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.domain.enrichment import EnrichStrategy


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    gemini_flash_model: str = "gemini-2.0-flash"
    gemini_pro_model: str = "gemini-2.0-pro"
    chroma_path: str = "data/chroma"
    tipi_data_dir: str = "data/tipi"
    confidence_threshold: float = 0.7
    ncm_chapter: str = "22"
    # Document-enrichment strategy (env: ENRICH_STRATEGY). OFF keeps the
    # ADR-0004 baseline (63.3% top-3); FULL is the ADR-0005 experiment (net
    # regression, kept reproducible); SUBHEADING_ONLY is ADR-0006 Form B
    # (inject the 6-digit product level, never the broad heading). The index
    # must be rebuilt to match; the adapter enforces index<->strategy agreement.
    enrich_strategy: EnrichStrategy = EnrichStrategy.OFF


# NOTE: instantiates at import time. CI environments must provide
# GEMINI_API_KEY (placeholder OK for skeleton).
# See .github/workflows/eval.yml.
settings = Settings()
