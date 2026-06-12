from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    gemini_flash_model: str = "gemini-2.0-flash"
    gemini_pro_model: str = "gemini-2.0-pro"
    chroma_path: str = "data/chroma"
    tipi_data_dir: str = "data/tipi"
    confidence_threshold: float = 0.7
    ncm_chapter: str = "22"
    # ADR-0005: hierarchical document enrichment. Default off — naive
    # enrichment is a net regression (top-3 63.3% -> 53.3%). The index must be
    # rebuilt to match this flag; the adapter enforces index<->flag agreement.
    enrich_documents: bool = False


# NOTE: instantiates at import time. CI environments must provide
# GEMINI_API_KEY (placeholder OK for skeleton).
# See .github/workflows/eval.yml.
settings = Settings()
