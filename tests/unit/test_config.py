"""Settings defaults that pin production behavior (ADR-0007/0008).

These assert the declared field defaults (env-independent) so production stays on
the ADR-0007 baseline regardless of any EMBEDDER value in the ambient env.
"""

import pytest

from src.config import Settings
from src.core.domain.enrichment import EnrichStrategy
from src.retrieval.embedding import EmbedderModel


def test_settings_instantiates_without_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Gemini rerank path is not yet implemented, so a key is not required to
    # run the shipping pipeline. _env_file=None ignores any local .env.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.gemini_api_key is None


def test_embedder_defaults_to_e5_small() -> None:
    # Production default is the ADR-0004/0007 baseline embedder; bge-m3 is opt-in
    # via EMBEDDER for the ADR-0008 probe, never the default until an ADR ships it.
    assert Settings.model_fields["embedder"].default is EmbedderModel.E5_SMALL


def test_enrich_strategy_defaults_to_off() -> None:
    assert Settings.model_fields["enrich_strategy"].default is EnrichStrategy.OFF


def test_llm_provider_defaults_to_google() -> None:
    # ADR-0016: generic provider config replacing Gemini-specific naming.
    assert Settings.model_fields["llm_provider"].default == "google"


def test_llm_model_defaults_to_gemini_flash() -> None:
    assert Settings.model_fields["llm_model"].default == "gemini-2.5-flash"
