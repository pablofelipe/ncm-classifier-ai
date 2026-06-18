"""Settings defaults that pin production behavior (ADR-0007/0008).

These assert the declared field defaults (env-independent) so production stays on
the ADR-0007 baseline regardless of any EMBEDDER value in the ambient env.
"""

from src.config import Settings
from src.core.domain.enrichment import EnrichStrategy
from src.retrieval.embedding import EmbedderModel


def test_embedder_defaults_to_e5_small() -> None:
    # Production default is the ADR-0004/0007 baseline embedder; bge-m3 is opt-in
    # via EMBEDDER for the ADR-0008 probe, never the default until an ADR ships it.
    assert Settings.model_fields["embedder"].default is EmbedderModel.E5_SMALL


def test_enrich_strategy_defaults_to_off() -> None:
    assert Settings.model_fields["enrich_strategy"].default is EnrichStrategy.OFF
