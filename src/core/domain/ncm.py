from dataclasses import dataclass, field
from typing import Literal, get_args

ConfidenceLabel = Literal["high", "needs_review"]


@dataclass(frozen=True)
class ProductQuery:
    product_name: str
    description: str


@dataclass
class ClassificationCandidate:
    ncm_code: str
    description: str
    score: float
    metadata: dict[str, str | float] = field(default_factory=dict)


def candidate_metadata_from_entry(entry: dict[str, object]) -> dict[str, str | float]:
    """Maps a TIPI JSON entry to the curated metadata exposed in
    ClassificationCandidate.

    Input is dict[str, object] (the natural form for both the JSON
    loaded by NaiveRetrievalAdapter and the metadata returned by
    ChromaRetrievalAdapter). Output is dict[str, str | float], the
    curated shape consumed by API and eval.

    This is the canonical mapping — both adapters must use it.
    """
    # FUTURE: when the system grows, consider introducing a TypedDict
    # for the input shape (TIPIEntryDict) to get static guarantees
    # about expected keys. For walking skeleton, dict[str, object]
    # is acceptable — runtime tests cover key presence.
    return {
        "ncm_dotted": str(entry["ncm"]),
        "chapter": str(entry["chapter"]),
        "heading": str(entry["heading"]),
        "subheading": str(entry["subheading"]),
        "description": str(entry["description"]),
        "ipi_rate": str(entry["ipi_rate"]),
    }


@dataclass(frozen=True)
class ClassificationResult:
    top_candidates: list[ClassificationCandidate]
    confidence_label: ConfidenceLabel

    def __post_init__(self) -> None:
        if len(self.top_candidates) != 3:
            raise ValueError(
                f"top_candidates must hold exactly 3 candidates, got {len(self.top_candidates)}"
            )
        if self.confidence_label not in get_args(ConfidenceLabel):
            raise ValueError(
                f"confidence_label must be one of {get_args(ConfidenceLabel)}, "
                f"got {self.confidence_label!r}"
            )
