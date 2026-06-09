from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ClassifyRequest(BaseModel):
    product_name: str = Field(..., max_length=200)
    description: str = Field(..., max_length=300)


class NCMCandidate(BaseModel):
    ncm: str  # dotted format, e.g. "2202.10.00"
    description: str  # TIPI description
    score: float  # candidate confidence score (0.0 to 1.0)


class ClassifyResponse(BaseModel):
    confidence_label: Literal["high", "needs_review"]
    candidates: list[NCMCandidate]  # exactly 3 in v1
    latency_ms: float  # measured at the route, not in the domain

    @model_validator(mode="after")
    def _exactly_three_candidates(self) -> "ClassifyResponse":
        if len(self.candidates) != 3:
            raise ValueError(
                f"candidates must contain exactly 3 items, got {len(self.candidates)}"
            )
        return self
