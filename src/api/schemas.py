from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ClassifyRequest(BaseModel):
    product_name: str = Field(..., max_length=200)
    description: str = Field(..., max_length=300)


class NCMCandidate(BaseModel):
    ncm: str  # formato dotted, ex. "2202.10.00"
    description: str  # descrição da TIPI
    score: float  # score de confiança do candidato (0.0 a 1.0)


class ClassifyResponse(BaseModel):
    confidence_label: Literal["high", "needs_review"]
    candidates: list[NCMCandidate]  # exatamente 3 no v1
    latency_ms: float  # medido na rota, não no domínio

    @model_validator(mode="after")
    def _exactly_three_candidates(self) -> "ClassifyResponse":
        if len(self.candidates) != 3:
            raise ValueError(
                f"candidates must contain exactly 3 items, got {len(self.candidates)}"
            )
        return self
