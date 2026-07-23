import re
from dataclasses import dataclass, field
from typing import Literal, get_args

ConfidenceLabel = Literal["high", "needs_review"]

NCM_CODE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


@dataclass(frozen=True)
class NCMCode:
    """8-digit NCM fiscal code, canonical dotted form (e.g. "2202.10.00")."""

    value: str

    def __post_init__(self) -> None:
        if not NCM_CODE_RE.fullmatch(self.value):
            raise ValueError(f"invalid NCM code format: {self.value!r} (expected XXXX.XX.XX)")

    def __str__(self) -> str:
        return self.value

    @property
    def dotless(self) -> str:
        return self.value.replace(".", "")

    def matches_heading(self, heading: str) -> bool:
        """True if this code falls under the given heading (dotted or dotless)."""
        return self.dotless.startswith(heading.replace(".", ""))


@dataclass(frozen=True)
class ProductQuery:
    product_name: str
    description: str


@dataclass
class ClassificationCandidate:
    ncm_code: NCMCode
    description: str
    score: float
    metadata: dict[str, str | float] = field(default_factory=dict)


def candidate_metadata_from_entry(entry: dict[str, object]) -> dict[str, str | float]:
    """Maps a raw TIPI JSON entry to the curated metadata exposed in
    ClassificationCandidate.

    Used by NaiveRetrievalAdapter, which reads TIPI JSON entries directly.
    ChromaRetrievalAdapter does NOT use it: it builds candidate metadata from
    the metadata stored on the Chroma collection at index time (see
    src/retrieval/hierarchical.py). Output is dict[str, str | float], the
    curated shape consumed by API and eval.
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
    escalation_reason: str | None = None

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
