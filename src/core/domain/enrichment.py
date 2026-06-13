from enum import StrEnum


class EnrichStrategy(StrEnum):
    """Document-text enrichment strategy for the TIPI index.

    The value is the string stored as Chroma collection metadata and read from
    the ENRICH_STRATEGY env var, so index and config can be checked for
    agreement (see ChromaRetrievalAdapter).

    - OFF: raw 8-digit (leaf) description, byte-for-byte — the ADR-0004 baseline.
    - FULL: heading + subheading + cleaned leaf — the ADR-0005 experiment
      (net regression, kept reproducible behind the flag).
    - SUBHEADING_ONLY: cleaned subheading (the 6-digit "product" level of the
      Harmonized System) + cleaned leaf, when the subheading is substantive;
      the 4-digit heading (broad family) is never injected — ADR-0006, Form B.
    """

    OFF = "off"
    FULL = "full"
    SUBHEADING_ONLY = "subheading_only"
