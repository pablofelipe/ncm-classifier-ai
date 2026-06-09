from typing import Literal

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    product_name: str = Field(..., max_length=200)
    description: str = Field(..., max_length=300)


class NCMCandidate(BaseModel):
    code: str
    description: str
    confidence: float
    rationale: str


class ClassifyResponse(BaseModel):
    status: Literal["confident", "escalate"]
    candidates: list[NCMCandidate]
    verification_passed: bool
