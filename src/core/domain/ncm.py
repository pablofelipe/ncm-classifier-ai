from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProductQuery:
    product_name: str
    description: str


@dataclass
class ClassificationCandidate:
    ncm_code: str
    description: str
    score: float
    metadata: dict = field(default_factory=dict)
